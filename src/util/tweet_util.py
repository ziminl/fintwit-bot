## > Imports
# > Standard libaries
from __future__ import annotations
from typing import Optional, List
import datetime
from traceback import format_exc

# Discord imports
import discord
from discord.ext import commands

# 3rd party imports
import pandas as pd
import numpy as np

# Local dependencies
import util.vars
from util.ticker_classifier import classify_ticker, get_financials
from util.sentiment_analyis import add_sentiment
from util.disc_util import get_emoji
from util.vars import filter_dict, get_json_data, bearer_token
from util.db import merge_and_update, remove_old_rows


async def format_tweet(
    as_json: dict,
) -> Optional[
    tuple[str, str, str, str, List[str], List[str], List[str], Optional[str]]
]:
    """
    Gets all the useful infromation from the raw_data.
    Checks if the tweet is from someone we follow.

    Parameters
    ----------
    as_json : dict
        The data from the tweet.
    following_ids : List[str]
        The list of the ids of the people we follow.

    Returns
    -------
    Optional[tuple[str, str, str, str, List[str], List[str], List[str], Optional[str]]]
        str
            The text of the tweet.
        str
            The user that tweeted.
        str
            The url to the user's profile pic.
        str
            The url to the tweet.
        List[str]
            The images in the tweet.
        List[str]
            The tickers in the tweet.
        List[str]
            The hashtags in the tweet.
        Optional[str]
            The user that was retweeted.
    """

    #print(as_json)

    # Get the user name
    if "includes" in as_json.keys():
        user = as_json["includes"]["users"][0]["username"]

        # Get other info
        profile_pic = as_json["includes"]["users"][0]["profile_image_url"]

        # Could also use ['id_sr'] instead
        url = f"https://twitter.com/{user}/status/{as_json['data']['conversation_id']}"
    else:
        print(as_json)

    (
        text,
        tickers,
        images,
        retweeted_user,
        hashtags,
    ) = await get_tweet(as_json)

    # Post tweets that contain images
    if text == "" and images == []:
        return

    # Replace &amp;
    text = text.replace("&amp;", "&")
    text = text.replace("&gt;", ">")
    text = text.replace("&lt;", "<")

    # Post the tweet containing the important info
    try:
        return (
            text,
            user,
            profile_pic,
            url,
            images,
            tickers,
            hashtags,
            retweeted_user,
        )

    except Exception:
        print(
            f"Error posting tweet of {user} at {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}"
        )
        print(format_exc())
        return


async def add_quote_tweet(
    quote_data, retweeted_user
):
    (
        user_text,
        user_ticker_list,
        user_image,
        user_hashtags,
    ) = await standard_tweet_info(quote_data, "quoted")

    text, ticker_list, image, hashtags = await standard_tweet_info(
        quote_data, "quoted tweet"
    )

    # Combine the information
    images = user_image + image
    ticker_list = user_ticker_list + ticker_list
    hashtags = user_hashtags + hashtags

    # Add > to show it's a quote
    if text != "":
        text = "\n".join(map(lambda line: "> " + line, text.split("\n")))

    text = f"{user_text}\n\n> [@{retweeted_user}](https://twitter.com/{retweeted_user}):\n{text}"

    return text, ticker_list, images, hashtags

def get_basic_tweet_info(as_json : dict) -> tuple[str, Optional[str]]:
    retweeted_user = None
    
    # Tweet type can be "retweeted", "quoted" or "replied_to"
    tweet_type = as_json["data"]["referenced_tweets"][0]["type"]

    # Set the retweeted / quoted user
    if tweet_type == "retweeted" or tweet_type == "quoted":
        if len(as_json["includes"]["users"]) > 1:
            retweeted_user = as_json["includes"]["users"][1]["username"]
        else:
            # If the user retweeted themselves
            retweeted_user = as_json["includes"]["users"][0]["username"]
            
    return tweet_type, retweeted_user


async def get_tweet(
    as_json: dict,
) -> tuple[str, List[str], List[str], Optional[str], List[str]]:
    """
    Returns the info of the tweet that was quote retweeted

    Parameters
    ----------
    as_json : dict
        The json object of the tweet.

    Returns
    -------
    tuple[str, List[str], List[str], Optional[str], List[str]]
        str
            The text of the tweet.
        List[str]
            The tickers in the tweet.
        List[str]
            The images in the tweet.
        Optional[str]
            The user that was retweeted.
        List[str]
            The hashtags in the tweet.
    """

    # Check for any referenced tweets
    if "referenced_tweets" in as_json["data"].keys():
        tweet_type, retweeted_user = get_basic_tweet_info(as_json)
        
        # Could also add the tweet that it was replied to
        if tweet_type == "replied_to":
            return "", [], [], None, []

        # If it is a retweet change format
        if tweet_type == "retweeted":
            # Only do this if a quote tweet was retweeted
            if (
                "referenced_tweets" in as_json["includes"]["tweets"][-1].keys()
                and as_json["includes"]["tweets"][-1]["referenced_tweets"][0]["type"]
                == "quoted"
            ):
                quote_data = await get_json_data(
                    url=f"https://api.twitter.com/2/tweets/{as_json['includes']['tweets'][-1]['conversation_id']}?tweet.fields=attachments,entities,conversation_id&expansions=attachments.media_keys,referenced_tweets.id&media.fields=url",
                    headers={"Authorization": f"Bearer {bearer_token}"},
                )

                text, ticker_list, images, hashtags = await add_quote_tweet(
                    quote_data,
                    retweeted_user,
                )

            # Standard retweet
            else:
                (text, ticker_list, images, hashtags,) = await standard_tweet_info(
                    as_json, "retweeted"
                )

        # Add the user text to it
        elif tweet_type == "quoted":
            text, ticker_list, images, hashtags = await add_quote_tweet(
                as_json,
                retweeted_user,
            )

    # If there is no reference then it is a normal tweet
    else:
        retweeted_user = None
        
        text, ticker_list, images, hashtags = await standard_tweet_info(
            as_json, "tweet"
        )

    try:
        return text, ticker_list, images, retweeted_user, hashtags
    except Exception as e:
        print("Error processing tweet, error:", e)
        print(as_json)


def get_tweet_img(as_json: dict) -> List[str]:
    images = []

    # Check for images
    if "includes" in as_json.keys():
        if "media" in as_json["includes"].keys():
            for media in as_json["includes"]["media"]:
                if media["type"] == "photo":
                    images.append(media["url"])
                    
    return images

def get_tags(as_json: dict, keyword : str) -> List[str]:
    """
    Gets the hashtags or cashtags from the tweet.

    Parameters
    ----------
    as_json : dict
        The json object of the tweet.
    keyword : str
        Can be "hashtags" or "cashtags".

    Returns
    -------
    List[str]
        The tags in the tweet text.
    """

    tags = []
    if "entities" in as_json.keys():
        if keyword in as_json["entities"].keys():
            for tag in as_json["entities"][keyword]:
                tags.append(tag["tag"])

    return tags

async def get_missing_img(conversation_id : str) -> List[str]:
    image_data = await get_json_data(
        url=f"https://api.twitter.com/2/tweets/{conversation_id}?expansions=attachments.media_keys&media.fields=url",
        headers={"Authorization": f"Bearer {bearer_token}"},
    )
    return get_tweet_img(image_data)

async def standard_tweet_info(
    as_json: dict, tweet_type: str = "tweet"
) -> tuple[str, List[str], List[str], List[str]]:
    """
    Returns the text, tickers, images, and hashtags of a tweet.

    Parameters
    ----------
    as_json : dict
        The json object of the tweet.
    tweet_type: str
        The type of tweet, can be "quoted", "retweet", "replied_to" or "tweet".

    Returns
    -------
    tuple[str, List[str], List[str], List[str]]
        str
            The text of the tweet.
        List[str]
            The tickers in the tweet.
        List[str]
            The images in the tweet.
        List[str]
            The hashtags in the tweet.
    """    
    # Check for images, do not do this for quoted tweet, otherwise images will get added twice
    images = []
    if tweet_type != "quoted tweet":
        images = get_tweet_img(as_json)

    # Unpack json data
    if tweet_type == "tweet" or tweet_type == "quoted":
        tweet_data = as_json["data"]
    elif tweet_type == "retweeted" or tweet_type == "quoted tweet":
        tweet_data = as_json["includes"]["tweets"][-1]
        
    text = tweet_data["text"]

    # Remove image urls and extend other urls
    if "entities" in tweet_data.keys():
        if "urls" in tweet_data["entities"].keys():
            for url in tweet_data["entities"]["urls"]:
                if "media_key" in url.keys():
                    text = text.replace(url["url"], "")
                    # If there are no images yet, get the image based on conversation id
                    if images == []:
                        images = await get_missing_img(tweet_data["conversation_id"])
                else:
                    if tweet_type == "quoted" and url["expanded_url"].startswith(
                        "https://twitter.com"
                    ):
                        # If it is a quote and the url is a twitter url, remove it
                        text = text.replace(url["url"], "")
                    else:
                        text = text.replace(url["url"], url["expanded_url"])
                        
    tickers = get_tags(tweet_data, "cashtags")
    hashtags = get_tags(tweet_data, "hashtags")

    return text, tickers, images, hashtags


def get_clean_symbols(tickers, hashtags):

    # First remove the duplicates
    symbols = list(set(tickers + hashtags))

    clean_symbols = []

    # Check the filter dict
    for symbol in symbols:

        # Filter beforehand
        if symbol in filter_dict.keys():
            # For instance Ethereum -> ETH
            new_sym = filter_dict[symbol]
            # However if ETH is in there we do not want to have it twice
            if new_sym not in clean_symbols:
                clean_symbols.append(new_sym)
        else:
            clean_symbols.append(symbol)

    return clean_symbols


def format_description(
    AH: bool, change: list, price: list, website: str, i: int
) -> str:
    if AH:
        return f"[AH: ${price[i]}\n({change[i]})]({website})\n"
    else:
        return f"[${price[i]}\n({change[i]})]({website})"


def get_description(change, price, website):
    # Change can be a list (if the information is from Yahoo Finance) or a string
    if type(change) == list and type(price) == list:
        # If the length is 2 then we know the after-hour prices
        if len(change) == 2 and len(price) == 2:
            for i in range(len(change)):
                if i == 0:
                    description = format_description(True, change, price, website, i)
                else:
                    description += format_description(False, change, price, website, i)
        else:
            return format_description(False, change, price, website, 0)

    else:
        return format_description(False, [change], [price], website, 0)

    return description


async def add_financials(
    e: discord.Embed,
    tickers: List[str],
    hashtags: List[str],
    text: str,
    user: str,
    bot: commands.Bot,
) -> tuple[discord.Embed, str, str, List[str], List[str]]:
    """
    Adds the financial data to the embed and returns the corresponding category.

    Parameters
    ----------
    e : discord.Embed
        The embed to add the data to.
    tickers : List[str]
        The tickers in the tweet.
    hashtags : List[str]
        The hashtags in the tweet.
    text : str
        The text of the tweet.
    user : str
        The user that tweeted.
    bot : commands.Bot
        The bot object, used for getting the custom emojis.

    Returns
    -------
    tuple[discord.Embed, str, str]
        discord.Embed
            The embed with the data added.
        str
            The category of the tweet.
        str
            The sentiment of the tweet.
        List[str]
            The base symbols of the tickers.
        List[str]
            The category of each ticker.
    """

    # In case multiple tickers get send
    crypto = 0
    stocks = 0
    forex = 0

    # Get the unique values
    symbols = get_clean_symbols(tickers, hashtags)

    base_symbols = []
    categories = []
    do_last = []
    classified_tickers = []
    
    if not util.vars.classified_tickers.empty:
        # Drop tickers older than 3 days
        util.vars.classified_tickers = remove_old_rows(util.vars.classified_tickers, 3)
        classified_tickers = util.vars.classified_tickers['ticker'].tolist()

    for ticker in symbols:

        if crypto > stocks and crypto > forex:
            majority = "crypto"
        elif stocks > crypto and stocks > forex:
            majority = "stocks"
        elif forex > crypto and forex > stocks:
            majority = "forex"
        else:
            majority = "Unknown"

        # Get the information about the ticker
        if ticker not in classified_tickers:
            ticker_info = await classify_ticker(ticker, majority)
            if ticker_info:
                (
                    _,
                    website,
                    exchanges,
                    price,
                    change,
                    four_h_ta,
                    one_d_ta,
                    base_symbol,
                ) = ticker_info
                
                # Convert info to a dataframe
                df = pd.DataFrame([{'ticker':ticker,
                                    'website':website,
                                    'exchanges':exchanges,
                                    'base_symbol':base_symbol,
                                    'timestamp':datetime.datetime.now()}])
                
                # Save the ticker info in a database
                try:
                    merge_and_update(util.vars.classified_tickers, df, 'classified_tickers')
                except Exception as e:
                    print("Error while saving classified tickers:", e)
                    print(df)

                # Skip if this ticker has been done before, for instance in tweets containing Solana and SOL
                if base_symbol in base_symbols:
                    continue

            else:
                if ticker in tickers:

                    e.add_field(name=f"${ticker}", value=majority)
                    print(
                        f"No crypto or stock match found for ${ticker} in {user}'s tweet at {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}"
                    )

                # Go to next in symbols
                continue
        else:
            ticker_info = util.vars.classified_tickers[util.vars.classified_tickers['ticker'] == ticker]
            
            website = ticker_info['website'].values[0]
            exchanges = ticker_info['exchanges'].values[0]
            base_symbol = ticker_info['base_symbol'].values[0]
            
            # Still need the price, change, TA info
            price, change, four_h_ta, one_d_ta = await get_financials(ticker, website)

        title = f"${ticker}"

        # Determine if this is a crypto or stock
        if website:
            if "coingecko" in website:
                crypto += 1
                categories.append("crypto")
                if exchanges:
                    if "Binance" in exchanges:
                        title = f"{title} {get_emoji(bot, 'binance')}"
                    if "KuCoin" in exchanges:
                        title = f"{title} {get_emoji(bot, 'kucoin')}"

            if "yahoo" in website:
                stocks += 1
                categories.append("stocks")
            if "forex" in website:
                forex += 1
                categories.append("forex")
        else:
            # Default category is crypto
            categories.append("crypto")

        base_symbols.append(base_symbol)

        # If there is no TA for a symbol, add it at the end of the embed
        if four_h_ta is None:
            do_last.append((title, change, price, website))
            continue

        # Add the field with hyperlink
        e.add_field(
            name=title, value=get_description(change, price, website), inline=True
        )

        e.add_field(name="4h TA", value=four_h_ta, inline=True)

        e.add_field(name="1d TA", value=one_d_ta, inline=True)

    for title, change, price, website in do_last:
        e.add_field(
            name=title, value=get_description(change, price, website), inline=True
        )

    # Finally add the sentiment to the embed
    if symbols:
        e, prediction = add_sentiment(e, text)
    else:
        prediction = None

    # Decide the category of this tweet
    if crypto == 0 and stocks == 0 and forex == 0:
        category = None
    else:
        category = ("crypto", "stocks", "forex")[np.argmax([crypto, stocks, forex])]

    # Return just the prediction without emoji
    return e, category, prediction, base_symbols, categories


async def count_tweets(ticker: str) -> int:
    """
    Counts the number of tweets for a ticker during the last 24 hours.
    https://developer.twitter.com/en/docs/twitter-api/tweets/counts/api-reference/get-tweets-counts-recent
    Max 300 requests per 15 minutes, so 20 requests per minute.

    Parameters
    ----------
    ticker : str
        The ticker to count the tweets for.

    Returns
    -------
    int
        Returns the number of tweets for the ticker.
    """

    # Count the last 24 hours
    # Can add -is:retweet in query param to exclude retweets
    start_time = (
        datetime.datetime.utcnow() - datetime.timedelta(days=1)
    ).isoformat() + "Z"
    url = f"https://api.twitter.com/2/tweets/counts/recent?query={ticker}&granularity=day&start_time={start_time}"
    counts = await get_json_data(
        url=url, headers={"Authorization": f"Bearer {bearer_token}"}
    )

    if "meta" in counts.keys():
        if "total_tweet_count" in counts["meta"].keys():
            return counts["meta"]["total_tweet_count"]
