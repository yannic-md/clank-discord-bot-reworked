<h1 align="center">⚠️ THIS PROJECT IS STILL UNDER DEVELOPMENT AND DOESN'T REPRESENT THE PUBLIC VERSION OF THIS BOT YET. ⚠️</h1>

<h1 align="center">
    🤖 Clank ~ Discord-Bot
</h1>

<p align="center">
  <i align="center">Clank is a multifunctional Discord bot designed to enhance server management with unique features.<br />Developed by Discord server owners for discord server owners - ensuring a high level of quality and love. 💝</i>
</p>

<h4 align="center">
  <a href="https://www.sqlalchemy.org/">
    <img src="https://img.shields.io/badge/sqlalchemy-2.0.51-2980b9?style=for-the-badge" alt="sqlalchemy version" style="height: 25px;">
  </a>
  <a href="https://github.com/long2ice/asyncmy">
    <img src="https://img.shields.io/badge/asyncmy-0.2.11-2980b9?style=for-the-badge" alt="asyncmy version" style="height: 25px;">
  </a>
  <a href="https://alembic.sqlalchemy.org/en/latest/">
    <img src="https://img.shields.io/badge/alembic-1.18.5-2980b9?style=for-the-badge" alt="alembic version" style="height: 25px;">
  </a>
  <br />
  <a href="https://docs.python.org/3.14/whatsnew/3.14.html">
    <img src="https://img.shields.io/badge/python-3.14-2980b9?style=for-the-badge" alt="python version" style="height: 25px;">
  </a>
  <a href="https://github.com/Rapptz/discord.py">
    <img src="https://img.shields.io/badge/discord.py-2.7.1-2980b9?style=for-the-badge" alt="library version" style="height: 25px;">
  </a>
  <br />
  <a href="https://discord.gg/bl4cklist">
    <img src="https://img.shields.io/discord/616655040614236160?style=for-the-badge&logo=discord&label=Discord&color=%237289da" alt="discord server" style="height: 25px;">
  </a>
  <br>
</h4>

## 🗯️ ~ Introduction

› `Clank` is a multifunctional Discord bot written in Python, designed with unique features to enhance server
management. It offers various modules that users can activate or deactivate based on their preferences. Additionally, it
provides an extensive range of customizable settings to tailor the bot’s functionality to each individual server.

💓 - Developed by Discord server owners for Discord server owners, Clank prioritizes quality and meticulous attention to
detail. The support team promptly addresses bug reports and offers a wealth of documentation to assist users.

› The <strong>primary goal</strong> of this bot is to replace as many external Discord bots as possible, minimizing
reliance on third-party bots.

## 🪛 ~ Module list

› `Clank` offers a wide range of integrated modules for discord server owners to manage as they see a need. This is
useful in cases where you don't want to use an integrated module or want to customize it in a way you like.

Currently it supports the <strong>following modules</strong>:
<ul>
  <li>🎨 <strong>Embed-& Container Builder</strong>: Create helpful informational messages (using embeds and containers) directly within Discord via intuitive buttons, and save your templates for later.</li>
  <br />
  <li>🎁 <strong>Giveaway-System</strong>: This module offers an entire system to manage giveaways on your discord guild. You can track guild invites, select a sponsor, set a giveaway participation requirement and some design features. Gift your loved community a thing you like!</li>
  <br />
  <li>🚑 <strong>Support-System</strong>: This module provides a ticket system that operates via direct messages from server members. It also offers an FAQ system and informative messages for ticket creators, ensuring a user-friendly experience.</li>
  <br />
  <li>🚨 <strong>Security-System</strong>: This module safeguards your server against join raids and potential server nukes. It also can create AutoMod rules to protect against spam content and provides much tools for an easy moderation on your guild.</li>
  <br />
  <li>🌍 <strong>Global-Chat</strong>: With this module, you can chat with Discord users across other discord-servers without requiring them to be a member on your server - It provides an active chat environment without the need for moderation.</li>
</ul>

Additionally, we have plans for <strong>more modules</strong> in the future, and existing features will continue to be
refined. The development team actively listens to user suggestions, which can be submitted on
our <strong>[Discord server](https://discord.gg/bl4cklist)</strong>. 🌟

## 🤖 ~ Using our bot

To get started with our own discord bot, you can just <a href="https://bl4cklist.de/invites/clank-bot"><strong>
invite</strong></a> the bot to your discord server by visiting the link.

<hr>

## 🤝 ~ Development

› We love to hear that you would like to support our project! In this section, we explain a few important things in case
you want to develop this project with us.

### Add a new language

1. Fork the repository and create a branch for your changes.
2. Register the language to `SupportedLanguage`
   in <a href="https://github.com/yannic-md/clank-discord-bot-reworked/blob/main/core/enums/language.py" target="_blank">
   `core/enums/language.py`</a>.
3. Create the lang files in `locales/<code>/` with the same files/keys
   as <a href="https://github.com/yannic-md/clank-discord-bot-reworked/tree/main/locales/en" target="_blank">
   `locales/en/`</a>
4. Map the Discord client locale to it in `_DISCORD_LOCALE_TO_LANGUAGE`
   (<a href="https://github.com/yannic-md/clank-discord-bot-reworked/blob/main/core/i18n/discord_translator.py" target="_blank">
   `core/i18n/discord_translator.py`</a>).
5. Add a `Choice` for it in both `@choices(...)` blocks
   in <a href="https://github.com/yannic-md/clank-discord-bot-reworked/blob/main/features/settings/language_commands.py#L115" target="_blank">
   `features/settings/language_commands.py`</a>.
6. If it needs more plural forms than `"one"`/`"other"`, add a rule to `_PLURAL_RULES`
   (<a href="https://github.com/yannic-md/clank-discord-bot-reworked/blob/main/core/i18n/translator.py" target="_blank">
   `core/i18n/translator.py`</a> - like for Russia, Polish, Arabic, ..)
7. Update the database for the language by using these commands:<br />-
   `alembic revision --autogenerate -m "Add <LANGUAGE HERE> to supported languages"`<br />- `alembic upgrade head`
8. Push your branch and open a pull request.