#!/usr/local/bin/python3

import discord
import requests
from datetime import datetime
import json
import asyncio
import os

import constants

class Logger:
	logfile = None
	flush_handle = None
	
	def __init__(self):
		try:
			self.logfile = open(constants.log_file_path, "a")
		except:
			exit(1)
	
	def log(self, message):
#		print(message)
		if self.logfile:
			self.logfile.write("[{}] {}\n".format(datetime.now().strftime("%m/%d/%Y %I:%M:%S %p"), message))
			
			# flush file to disk after a while
			if self.flush_handle:
				self.flush_handle.cancel()
			self.flush_handle = asyncio.get_running_loop().call_later(5, self.flush)
	
	def flush(self):
		if self.logfile:
			self.logfile.flush()

settings = {}
our_guild = None
our_channel = None
message_associations = {}
intents = discord.Intents.default()
intents.members = True
intents.messages = True
client = discord.Client(intents = intents)
logger = Logger()

def to_real_emoji(emoji):
	# convert emoji name into real emoji object
	real_emoji = emoji
	if ord(emoji[0]) < 128:
		for e in our_guild.emojis:
			if e.name == emoji:
				real_emoji = e
				break
	return real_emoji

# emoji can be a string or an emoji object; return a string regardless
def emoji_name(emoji):
	if type(emoji) is str:
		return emoji
	else:
		return emoji.name

# started up
@client.event
async def on_ready():
	logger.log("Running")
	
	# load settings from file and update messages
	try:
		settings_file = open(constants.settings_file_path, "r")
		[message, success] = load_settings(settings_file.read())
		logger.log(message)
		settings_file.close()
		if success:
			await update_messages()
	except Exception as e:
		logger.log("Load config error: " + str(e))

# session resume
@client.event
async def on_resumed():
	logger.log("Resumed")

# connect
@client.event
async def on_connect():
	logger.log("Connected")

# disconnected
@client.event
async def on_disconnect():
	logger.log("Disconnected")

# when somone adds a reaction to a message
@client.event
async def on_raw_reaction_add(payload):
	# don't respond to our own reactions
	if payload.user_id == client.user.id:
		return
	
	# try to find role for this reaction
	try:
		role = message_associations[payload.message_id]["reactions"][emoji_name(payload.emoji)]
		member = our_guild.get_member(payload.user_id)
	except:
		return # reaction might not exist
	
	# add role to member
	try:
		await member.add_roles(role)
		logger.log("Added {} role to {} (#{})".format(role.name, member.name, member.id))
	except Exception as e:
		logger.log("Reaction add error: " + str(e))

# when somone removes a reaction from a message
@client.event
async def on_raw_reaction_remove(payload):
	# don't respond to our own reactions
	if payload.user_id == client.user.id:
		return
	
	# try to find role for this reaction
	try:
		role = message_associations[payload.message_id]["reactions"][emoji_name(payload.emoji)]
		member = our_guild.get_member(payload.user_id)
	except:
		return # reaction might not exist
	
	# remove role from member
	try:
		await member.remove_roles(role)
		logger.log("Removed {} role from {} (#{})".format(role.name, member.name, member.id))
	except Exception as e:
		logger.log("Reaction remove error: " + str(e))


# parse JSON string and load into global variables
# make sure there is enough info to reload the file again over DMs
def load_settings(input):
	global our_guild
	global our_channel
	global settings
	try:
		# parse JSON
		temp_settings = json.loads(input)
		
		# check if parsed JSON has all keys
		required_keys = ["guild", "channel", "reload_roles", "messages"]
		for key in required_keys:
			if key not in temp_settings:
				return "Missing \"{}\" key in JSON file!".format(key), False
		
		# verify content of guild, channel, and role keys
		n_matching_roles = 0
		for guild in client.guilds:
			if guild.id == temp_settings["guild"]:
				our_guild = guild
				
				for channel in guild.channels:
					if channel.id == temp_settings["channel"]:
						our_channel = channel
						
						guild_role_ids = [role.id for role in guild.roles]
						for role_id in temp_settings["reload_roles"]:
							if role_id in guild_role_ids:
								n_matching_roles += 1
					
						break
				
				break
			
		if n_matching_roles != len(temp_settings["reload_roles"]) or our_channel == None or our_guild == None:
			return "JSON does not match server", False
			
	except:
		return "JSON parsing error", False
	
	# commit settings
	settings = temp_settings
	return "Successfully loaded config file", True

# update any messages we've sent in the past, delete unneeded ones,
# and send new ones
async def update_messages():
	global message_associations
	global settings
	
	message_associations = {}
	success = 1
	
	# convert role IDs into role objects
	for m in settings["messages"]:
		reactions = m["reactions"]
		for emoji in reactions:
			id = reactions[emoji]
			for role in our_guild.roles:
				if id == role.id:
					reactions[emoji] = role
					break
	
	try:
		# load messages in given channel
		old_messages = [m async for m in our_channel.history()]
		
		new_messages = settings["messages"]
		n_messages = len(new_messages)
		
		# store how likely each old message is to be one of the new ones
		correlations = {}
		
		i = 0
		while i < len(old_messages):
			old_message = old_messages[i]
			
			# filter out messages not from bot
			if old_message.author.id != client.user.id:
				old_messages.remove(old_message)
				continue
			
			# try to find best match for each message based on roles of users with reactions
			correlations[old_message.id] = [0] * n_messages
			for old_reaction in old_message.reactions:
				for user in [u async for u in old_reaction.users()]:
					# ignore our own
					if user.id == client.user.id:
						continue
					
					# check if user that reacted has the correct role for one of the known messages
					try:
						for j in range(n_messages):
							new_reactions = new_messages[j]["reactions"]
							if emoji_name(old_reaction.emoji) in new_reactions and new_reactions[emoji_name(old_reaction.emoji)] in user.roles:
								correlations[old_message.id][j] += 1
#								print("user {} reacted to {} and has role {}".format(user.id, old_message.id, new_reactions[emoji_name(old_reaction.emoji)]))
					except Exception as e:
						logger.log("Message association error: " + str(e))
						success = 0
			i += 1
		
		# finalize associations for all new messages
		
		# create embed
		def create_embed(message):
			color = message["color"][0] << 16 | message["color"][1] << 8 | message["color"][2]
			return discord.Embed(title = message["title"], color = color, description = message["message"])
		
		# helper function to associate an old message ID with a new message object
		async def associate_messages(from_msg, to_msg):
			global message_associations
			message_associations[from_msg.id] = to_msg
			logger.log("Associated old message {} with {}".format(from_msg.id, to_msg))
			
			# update message content
			embed = create_embed(to_msg)
			if embed not in from_msg.embeds:
				await from_msg.edit(embed = embed)
				
			# update emoji list if needed
			for reaction in from_msg.reactions:
				if reaction.me and emoji_name(reaction.emoji) not in to_msg["reactions"]:
					logger.log("Clearing reactions because they're different")
					await reaction.clear()
					break
			for reaction in to_msg["reactions"]:
				try:
					await from_msg.add_reaction(to_real_emoji(reaction))
				except Exception as e:
					logger.log("Associated message emoji add error: " + str(e))
					return False
			return True
		
		# check for the best matching old message for each new message
		i = 0
		updated_new_messages = []
		updated_old_messages = old_messages
		while i < len(new_messages):
			max_correlation = 0
			max_correlation_message = None
			for old_message in old_messages:
				if correlations[old_message.id][i] > max_correlation:
					max_correlation = correlations[old_message.id][i]
					max_correlation_message = old_message
			
			if max_correlation_message != None:
				target_association = new_messages[i]
				success_temp = await associate_messages(max_correlation_message, target_association)
				if not success_temp:
					success = -1
				
				# don't need to deal with this old message anymore
				updated_old_messages.remove(max_correlation_message)
			else:
				# new message wasn't a match for anything
				updated_new_messages.append(new_messages[i])
			i += 1
		
		new_messages = updated_new_messages
		old_messages = updated_old_messages
		
		# try to match remaining messages based on title content
		updated_new_messages = []
		for new_message in new_messages:
			found = False
			for old_message in old_messages:
				if new_message["title"] in [e.title for e in old_message.embeds]:
					success_temp = await associate_messages(old_message, new_message)
					if not success_temp:
						success = -1
					
					updated_old_messages.remove(old_message)
					found = True
					break
			if not found:
				updated_new_messages.append(new_message)
			
		new_messages = updated_new_messages
		old_messages = updated_old_messages
		
		# delete unneeded messages
		for old_message in old_messages:
			logger.log("Deleting old message {}".format(old_message.id))
			await old_message.delete()
		
		# send new messages
		for new_message in new_messages:
			logger.log("Sending new message {}".format(new_message))
			m = await our_channel.send(embed = create_embed(new_message))
			message_associations[m.id] = new_message
			for emoji in new_message["reactions"]:
				try:
					await m.add_reaction(to_real_emoji(emoji))
				except Exception as e:
					logger.log("New message emoji add error: " + str(e))
					success = -1
					break
		
	except Exception as e:
		logger.log("Message update error: " + str(e))
		success = 0
		return success
	
	if success > 0:
		logger.log("Successfully updated messages")
	
	return success

# monitor for DMs
@client.event
async def on_message(message):
	# ignore anything that isn't a DM
	if type(message.channel) is not discord.DMChannel:
		return
	
	# make sure sender has the correct role on the target guild
	roles = [r.id for r in our_guild.get_member(message.author.id).roles]
	found = False
	for r in roles:
		if r in settings["reload_roles"]:
			found = True
			break
	if not found:
		return
	
	# respond to reload command by fetching new config JSON from web
	if message.content.lower() == "reload":
		logger.log("Reload requested by {} (#{})".format(message.author.name, message.author.id))
		
		# download
		try:
			request = requests.get(constants.settings_url, timeout = 10)
		except Exception as e:
			message_result = "Request error: " + str(e)
			logger.log(message_result)
			await message.channel.send(content = message_result)
		
		# check status code
		if request.status_code != 200:
			message_result = "Request from {} failed with status code {}".format(constants.settings_url, request.status_code)
			logger.log(message_result)
			await message.channel.send(content = message_result)
			return
		
		logger.log("Downloaded new config from {}".format(constants.settings_url))
		
		# parse data
		[message_result, success] = load_settings(request.text)
		logger.log(message_result)
		await message.channel.send(content = message_result)
		if not success:
			return # don't save an invalid file
		
		# save into local cache
		try:
			settings_file = open(constants.settings_file_path, "w")
			settings_file.write(request.text)
			settings_file.close()
		except:
			message_result = "Failed to save settings to {}".format(constants.settings_file_path)
			logger.log(message_result)
			await message.channel.send(content = message_result)
		
		# update messages
		success = await update_messages()
		if success > 0:
			await message.channel.send(content = "Successfully updated messages")
		elif success == -1:
			await message.channel.send(content = "Emoji error on message update")
		else:
			await message.channel.send(content = "Did not successfully update messages. Check log.")

async def main():
	logger.log("Bot starting")
	await client.start(constants.key)

asyncio.run(main())