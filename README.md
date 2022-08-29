# Role Bot
This is a Python-based bot that allows members of our Discord server to give themselves roles.

## `config.json`
* **"guild"** is the server ID that the bot will operate in.
* **"channel"** is the channel ID that the bot will operate in.
* **"reload_roles"** are the role IDs that are allowed to trigger a reload of the settings file by DMing the bot "reload".
* **"messages"** are the separate reactable messages the bot will send and maintain in the specified channel.
  - Messages are sent as embeds with the given title, message, and color.
  - The bot will try to re-use existing messages if the reactions and roles roughly match the new ones to avoid having to clear all reactions after a restart. If this fails, it will also match on titles.
  - The **"reactions"** dict pairs emojis to role IDs that will be assigned to members when they react with that emoji. Custom emojis can be used by putting the name instead of an emoji character.

Discord can be temperamental with emojis. You may need to remove extra unicode bytes to make it work with some.

## Required Discord Permissions
* Manage Roles
* Manage Messages
* Read Messages/View Channels
* Send Messages
