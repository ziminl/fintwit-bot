## > Imports
# > Standard libraries
from collections import Counter
import datetime

# > Discord dependencies
import discord
from discord.ext.tasks import loop

# Local dependencies
import util.vars
from util.vars import config
from util.disc_util import get_channel
from util.tweet_util import count_tweets


class Overview:
    def __init__(self, bot):
        self.bot = bot
        self.global_crypto = {}
        self.global_stocks = {}

        self.global_overview.start()

        if config["LOOPS"]["OVERVIEW"]["STOCKS"]["ENABLED"]:
            self.stocks_channel = get_channel(
                self.bot, config["LOOPS"]["OVERVIEW"]["CHANNEL"], config["CATEGORIES"]["STOCKS"]
            )
            self.do_stocks = True
        else:
            self.do_stocks = False

        if config["LOOPS"]["OVERVIEW"]["CRYPTO"]["ENABLED"]:
            self.crypto_channel = get_channel(
                self.bot, config["LOOPS"]["OVERVIEW"]["CHANNEL"], config["CATEGORIES"]["CRYPTO"]
            )
            self.do_crypto = True
        else:
            self.do_crypto = False

    async def overview(self, category, tickers, sentiment):
        # Make sure that the new db is not empty
        if not util.vars.tweets_db.empty:
            if self.do_stocks:
                await self.make_overview(category, tickers, sentiment)
            if self.do_crypto:
                await self.make_overview(category, tickers, sentiment)

    @loop(minutes=5)
    async def global_overview(self):
        categories = []
        if self.do_stocks:
            categories.append("stocks")
        if self.do_crypto:
            categories.append("crypto")

        for category in categories:
            db = util.vars.tweets_db.loc[util.vars.tweets_db["category"] == category]

            if db.empty:
                return

            # Get the top 50 mentions
            top50 = db["ticker"].value_counts()[:50]

            for ticker, _ in top50.items():
                # Get the global tweets about the ticker using the API
                if category == "stocks":
                    global_mentions = await count_tweets(ticker)
                    if global_mentions is not None:
                        self.global_stocks[ticker] = global_mentions
                elif category == "crypto":
                    global_mentions = await count_tweets(ticker)
                    if global_mentions is not None:
                        self.global_crypto[ticker] = await count_tweets(ticker)

    async def make_overview(
        self, category: str, tickers: list, last_sentiment: str
    ):
        # Post the overview for stocks and crypto
        db = util.vars.tweets_db.loc[util.vars.tweets_db["category"] == category]

        if db.empty:
            return

        # Get the top 50 mentions
        top50 = db["ticker"].value_counts()[:50]

        # Make the list for embeds
        count_list = []
        ticker_list = []
        sentiment_list = []

        # Add overview of sentiment for each ticker
        for ticker, count in top50.items():

            # Get the sentiment for the ticker
            sentiment = db.loc[db["ticker"] == ticker]["sentiment"].tolist()

            # Convert sentiment into a single str, i.e. "6🐂 2🦆 2🐻"
            sentiment = dict(Counter(sentiment))

            formatted_sentiment = ""
            # Use this method to sort the dict
            for emoji in ["🐂", "🦆", "🐻"]:
                if emoji in sentiment.keys():
                    if emoji == last_sentiment and ticker in tickers:
                        formatted_sentiment += f"**{sentiment[emoji]}**{emoji} "
                    else:
                        formatted_sentiment += f"{sentiment[emoji]}{emoji} "

            if category == "stocks":
                if ticker in self.global_stocks.keys():
                    count = f"{count} - {self.global_stocks[ticker]}"

            if category == "crypto":
                if ticker in self.global_crypto.keys():
                    count = f"{count} - {self.global_crypto[ticker]}"

            if ticker in tickers:
                # Make bold
                ticker = f"**{ticker}**"
                count = f"**{count}**"

            # Add count, symbol, sentiment to embed lists
            count_list.append(str(count))
            ticker_list.append(ticker)
            sentiment_list.append(formatted_sentiment)

        # Make the embed
        e = discord.Embed(
            title=f"Top {category.capitalize()} Mentions Of The Last 24 Hours",
            description="",
            color=0x090844,
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )

        e.add_field(
            name="Mentions",
            value="\n".join(count_list),
            inline=True,
        )

        e.add_field(
            name="Ticker",
            value="\n".join(ticker_list),
            inline=True,
        )

        e.add_field(
            name="Sentiment",
            value="\n".join(sentiment_list),
            inline=True,
        )

        if category == "crypto":
            # Delete previous message
            await self.crypto_channel.purge(limit=1)
            await self.crypto_channel.send(embed=e)
        else:
            await self.stocks_channel.purge(limit=1)
            await self.stocks_channel.send(embed=e)
