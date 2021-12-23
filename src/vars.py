# > 3rd Party Dependencies
import yaml
import tweepy

# Read config.yaml content
with open("config.yaml", "r", encoding="utf-8") as f:
    config = yaml.full_load(f)

# Set variables
consumer_key = config['TWITTER']['CONSUMER_KEY']
consumer_secret = config['TWITTER']['CONSUMER_SECRET']
access_token = config['TWITTER']['ACCESS_TOKEN_KEY']
access_token_secret = config['TWITTER']['ACCESS_TOKEN_SECRET']

# Init API
auth = tweepy.OAuthHandler(consumer_key, consumer_secret)
auth.set_access_token(access_token, access_token_secret)
api = tweepy.API(auth)