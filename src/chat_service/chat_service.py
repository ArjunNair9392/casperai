import os
import flask
import slack
import threading

from dotenv import load_dotenv
from flask import request, Flask, jsonify, Response

# Slack Libraries
from slack_bolt import App
from slack_sdk import WebClient
from slack_bolt.adapter.flask import SlackRequestHandler

# Local Python files
from chat_service_helper import connect_to_mongodb, chat, remove_ask_prefix

app = Flask(__name__)

load_dotenv()

# Initialize the app with your bot token and signing secret
slack_app = App(
    token=os.environ.get("SLACK_BOT_TOKEN"),
    signing_secret=os.environ.get("SLACK_SIGNING_SECRET")
)

# Create a request handler
handler = SlackRequestHandler(slack_app)


@app.route("/slack/events", methods=["POST"])
def slack_events():
    return handler.handle(request)


# Event listener for app installation
@slack_app.event("app_home_opened")
def handle_channel_creation(event, say):
    # Get the user ID of the installer
    user_id = event["user"]
    slack_bot_client = WebClient(token=os.getenv("SLACK_BOT_TOKEN"))
    slack_user_client = WebClient(token=os.getenv("SLACK_USER_TOKEN"))

    user_info_response = slack_bot_client.users_info(user=user_id)
    # Check if the API call was successful
    if user_info_response["ok"]:
        user_info = user_info_response["user"]
        user_email = user_info["profile"]["email"]

    db = connect_to_mongodb()

    users_collection = db['users']
    user = users_collection.find_one({"user_email": user_email})
    company_id = user['company_id']
    channels_collection = db['channels']
    channels = channels_collection.find({"company_id": company_id})
    channels = list(channels)

    if not user['slack_app_opened']:
        welcome_message = f"We have created {len(channels)} for you!"
        slack_bot_client.chat_postEphemeral(channel=user_id, text=welcome_message, user=user_id)
        result = users_collection.update_one(
            {"user_email": user_email},
            {"$set": {"slack_app_opened": True}}
        )
    try:
        if channels:
            for channel in channels:
                if channel['slack_channel_id'] == "":
                    # Create a private channel
                    channel_name = f"ask_{channel['channel_name'].replace(' ', '_').lower()}"
                    response = slack_user_client.conversations_create(
                        name=channel_name,
                        is_private=True
                    )

                    slack_channel_id = response["channel"]["id"]

                    # Get the bot user ID
                    auth_response = slack_bot_client.auth_test()
                    bot_user_id = auth_response['user_id']

                    # Invite the bot to the private channel
                    invite_response = slack_user_client.conversations_invite(
                        channel=slack_channel_id,
                        users=bot_user_id
                    )

                    result = channels_collection.update_one(
                        {"_id": channel['_id']},
                        {"$set": {"slack_channel_id": True}}
                    )

                    # Send a welcome message in the channel
                    welcome_message = "Welcome to our Slack workspace! We are excited to have you here."
                    slack_user_client.chat_postEphemeral(channel=slack_channel_id, text=welcome_message, user=user_id)
    except slack.errors.SlackApiError as e:
        if 'channel_already_exists' in str(e):
            print("Private channel already exists")
        else:
            print(f"Error creating channel: {e}")


def call_chat_service(user_id, channel_id, user_email, channel_name, query):
    res = chat(user_email, channel_name, query)

    # Send the final result to the user
    slack_client = WebClient(token=os.getenv("SLACK_BOT_TOKEN"))
    slack_response = slack_client.chat_postEphemeral(
        channel=channel_id,
        text=res,
        user=user_id
    )


@app.route('/ask-casper', methods=['POST'])
def test_call():
    slack_client = WebClient(token=os.getenv("SLACK_BOT_TOKEN"))
    data = request.form
    user_id = data.get('user_id')
    channel_id = data.get('channel_id')
    channel_name = data.get('channel_name')
    text = data.get('text')
    query = [{"role": "system",
              "content": "Your name is Casper. An incredibly intelligent, knowledgeable and quick-thinking AI, "
                         "that always replies with professionalism. Only respond based on the context I give you and "
                         "nothing outside that context. Also there can be"
                         "history associated with it so please use that."},
             {"role": "user", "content": text}]

    response_message = "Analyzing..."

    user_info = slack_client.users_info(user=user_id)
    user_email = user_info['user']['profile']['email']
    channel_name = remove_ask_prefix(channel_name)
    # Start the long-running task in a separate thread
    thread = threading.Thread(target=call_chat_service,
                              args=(data["user_id"], channel_id, user_email, channel_name, query))
    thread.start()

    slack_response = slack_client.chat_postEphemeral(
        channel=channel_id,
        text=response_message,
        user=user_id
    )

    return Response(), 200


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
