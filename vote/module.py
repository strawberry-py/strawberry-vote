import asyncio
import datetime
import emoji
import re
import dateutil.parser

from typing import Dict, List, Tuple

import discord
from discord.ext import commands

from pie import check, i18n, logger, utils

EMOJI_REGEX = "^<[a-zA-Z0-9]*:[a-zA-Z0-9]+:[0-9]*>$"

_ = i18n.Translator("modules/vote").translate

bot_log = logger.Bot.logger()
guild_log = logger.Guild.logger()


class Vote(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # Helper functions

    def check_emoji(
        self,
        emoji_str: str,
    ) -> bool:
        """Verifies if the str is valid emoji or not.
        Args:
            emoji_str: string to check
        Returns:
            True if it's known emoji
        """
        if emoji.is_emoji(emoji_str):
            return True

        if re.match(EMOJI_REGEX, emoji_str):
            found_emoji = discord.utils.get(
                self.bot.emojis, name=emoji_str.split(":")[1]
            )
            if not found_emoji:
                return False
            return True
        return False

    # Commands

    @commands.guild_only()
    @check.acl2(check.ACLevel.SUBMOD)
    @commands.command(name="vote")
    async def vote(self, ctx, endtime_str: str, *, options_str: str):
        """Start public voting.

        Args:
            endtime_str: Datetime string, preferably quoted.
            options_str: List of options.

        The time can be either delta from now (`3H`, `10m`, `1d`) or datetime string (`"24/12/2024 12:00"`)

        Each option must be on new line and must start with the emoji.
        For example:
        ```!vote 3H
        :one: Option one
        :two: Option two
        :custom_emoji: Option three```
        """
        try:
            end_time = utils.time.parse_datetime(endtime_str)
        except dateutil.parser.ParserError:
            await ctx.reply(
                _(
                    ctx,
                    "I don't know how to parse `{endtime_str}`, please try again.",
                ).format(endtime_str=endtime_str)
            )
            return

        options = {}

        for line in options_str.splitlines():
            try:
                (emoji_str, description) = line.split(maxsplit=1)
            except ValueError:
                await ctx.reply(
                    _(ctx, "Option `{option}` is in incorrect format.").format(
                        option=line
                    )
                )
                return
            if self.check_emoji(emoji_str):
                if emoji_str in options.keys():
                    await ctx.reply(
                        _(ctx, "Emoji {emoji_str} was used more than once!").format(
                            emoji_str=emoji_str
                        )
                    )
                    return
                options[emoji_str] = description
            else:
                await ctx.reply(
                    _(ctx, "Emoji {emoji_str} was not recognized as emoji!").format(
                        emoji_str=emoji_str
                    )
                )
                return

        vote = VoteObject(ctx, end_time, options)
        await vote.send_message()
        await vote.add_reactions()
        await vote.start()


class VoteObject:
    """Basic object to control Vote.

    Attributes:
        ctx: Command context for translation and reply purposes.
        end_time: Vote end time.
        options: Vote options.

    Args:
        ctx: Command context for translation and reply purposes.
        end_time: Vote end time.
        options: Dictionary where emoji as str is key and value as the description.
    """

    def __init__(self, ctx, end_time: datetime.datetime, options: Dict[str, str]):
        self.ctx = ctx
        self.end_time = end_time
        self.options = options

    async def send_message(self):
        """
        Sends the Vote message to the corresponding channel.
        """
        text = _(self.ctx, "Vote started!")
        text += "\n" + _(self.ctx, "**End time:** {end_time}").format(
            end_time=utils.time.format_datetime(self.end_time)
        )
        text += "\n" + _(self.ctx, "**Options:**")

        for emoji_str, option in self.options.items():
            text += "\n{emoji_str} - {option}".format(
                emoji_str=emoji_str, option=option
            )
        self.message = await self.ctx.send(text)

    async def add_reactions(self) -> bool:
        """
        Add reactions to the message.

        Returns: True if message exists, False otherwise
        """
        if not self.message:
            return False
        for emoji_str in self.options:
            await self.message.add_reaction(emoji_str)
        return True

    async def start(self):
        """
        (Passive) wait for the end of vote, then print the results.
        """
        await guild_log.info(self.ctx.author, self.ctx.channel, "Vote started!")
        await asyncio.sleep((self.end_time - datetime.datetime.now()).total_seconds())
        try:
            self.message = await self.message.channel.fetch_message(self.message.id)
        except Exception:
            await guild_log.warning(
                self.ctx.author,
                self.ctx.channel,
                "Vote ended but the message was not found!",
            )
            return

        votes = {}

        for reaction in self.message.reactions:
            emoji_str = str(reaction.emoji)
            if emoji_str not in self.options.keys():
                continue
            votes[emoji_str] = reaction.count - 1

        log_message: str = (
            "Vote ended: " + ", ".join(f"{v}x {k}" for k, v in votes.items()) + "."
        )

        await guild_log.info(self.ctx.author, self.ctx.channel, log_message)

        text = _(self.ctx, "Vote ended!") + "\n" + _(self.ctx, "**Results:**")

        sorted_votes: List[Tuple[str, int]] = sorted(
            votes.items(), key=lambda x: x[1], reverse=True
        )

        max_votes = sorted_votes[0][1]

        for emoji_str, vote_count in sorted_votes:
            option = self.options[emoji_str]
            if max_votes == vote_count:
                text += "\n**{vote_count}x {emoji} - {option}**".format(
                    vote_count=vote_count, emoji=emoji_str, option=option
                )
            else:
                text += "\n{vote_count}x {emoji} - {option}".format(
                    vote_count=vote_count, emoji=emoji_str, option=option
                )

        await self.ctx.send(text)


async def setup(bot) -> None:
    await bot.add_cog(Vote(bot))
