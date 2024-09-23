import os
import flask
import slack

from dotenv import load_dotenv
from flask import request, Flask, Response, jsonify

# Slack Libraries
from slack_bolt import App
from slack_sdk import WebClient
from slack_bolt.adapter.flask import SlackRequestHandler
from requests_futures.sessions import FuturesSession

# Local Python files
from chat_service_helper import connect_to_mongodb, remove_ask_prefix, fetch_index_name, multi_modal_rag_chain, \
    get_retriever, get_vectorestore, add_users, list_channels_for_user

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


@slack_app.event("app_home_opened")
def handle_channel_creation(event, say):
    # TODO: ONly create a channel when the admin of the channel opens the app.
    user_id = event["user"]
    slack_bot_client = WebClient(token=os.getenv("SLACK_BOT_TOKEN"))
    slack_user_client = WebClient(token=os.getenv("SLACK_USER_TOKEN"))
    try:
        user_info_response = slack_bot_client.users_info(user=user_id)
        if not user_info_response["ok"]:
            raise Exception("Failed to fetch user info")
        user_info = user_info_response["user"]
        user_email = user_info["profile"]["email"]
        auth_test_response = slack_bot_client.auth_test()
        team_id = auth_test_response['team_id']
        team_name = auth_test_response['team']
        db = connect_to_mongodb()
        users_collection = db['users']
        user = users_collection.find_one({"user_email": user_email})
        if not user:
            add_users(db, [user_email], user_id, team_id, team_name, False, '')
            welcome_message = (f"Welcome to CasperAI. Please visit this dashboard to create new channels and add files "
                               f"to be trained by our model, backed by chatGPT!")
            slack_bot_client.chat_postEphemeral(channel=user_id, text=welcome_message, user=user_id)
        else:
            if team_id not in user.get('slack_workspace', {}):
                users_collection.update_one(
                    {"user_email": user_email},
                    {"$set": {f"slack_workspace.{team_id}": team_name}}
                )

            if not user.get('slack_app_opened'):
                company_id = user.get('company_id')
                if not company_id:
                    print(f"Company ID not found for user {user_email}.")
                    return
                channels_collection = db['channels']
                channels = list(channels_collection.find({"company_id": company_id}))
                if channels:
                    for channel in channels:
                        if channel.get('slack_channel_id') == "" and channel.get('slack_workspace', {}).get(team_id) is not None:
                            try:
                                # Create a private channel
                                channel_name = f"ask_{channel['channel_name'].replace(' ', '_').lower()}"
                                response = slack_user_client.conversations_create(
                                    name=channel_name,
                                    is_private=True
                                )

                                slack_channel_id = response["channel"]["id"]
                                auth_response = slack_bot_client.auth_test()
                                bot_user_id = auth_response['user_id']
                                slack_user_client.conversations_invite(
                                    channel=slack_channel_id,
                                    users=bot_user_id
                                )
                                channel_info = slack_user_client.conversations_members(channel=slack_channel_id)
                                if user_id not in channel_info["members"]:
                                    # Invite the user to the private channel if not already a member
                                    slack_user_client.conversations_invite(
                                        channel=slack_channel_id,
                                        users=user_id
                                    )
                                else:
                                    print(f"User {user_email} is already a member of the channel {channel_name}.")

                                # Update the channel document with the Slack channel ID
                                channels_collection.update_one(
                                    {"_id": channel['_id']},
                                    {"$set": {"slack_channel_id": slack_channel_id}}
                                )

                                # Send a welcome message in the channel
                                welcome_message = "Welcome to our Slack workspace! We are excited to have you here."
                                slack_user_client.chat_postEphemeral(channel=slack_channel_id, text=welcome_message,
                                                                     user=user_id)

                            except slack.errors.SlackApiError as e:
                                if 'channel_already_exists' in str(e):
                                    print("Private channel already exists")
                                else:
                                    print(f"Error creating channel: {e}")
                welcome_message = f"Welcome to CasperAI. Already added user!"
                slack_bot_client.chat_postEphemeral(channel=user_id, text=welcome_message, user=user_id)
                users_collection.update_one(
                    {"user_email": user_email},
                    {"$set": {"slack_app_opened": True}}
                )

    except Exception as e:
        print(f"An error occurred: {e}")


# Event listener for member joining a channel
@slack_app.event("message")
def handle_member_joined_channel(body, log):
    slack_user_id = body['event']['user']
    channel_id = body['event']['channel']
    channel_sub_type = body['event']['subtype']
    slack_user_client = WebClient(token=os.getenv("SLACK_USER_TOKEN"))
    slack_bot_client = WebClient(token=os.getenv("SLACK_BOT_TOKEN"))
    user_info = slack_bot_client.users_info(user=slack_user_id)
    user_email = user_info['user']['profile']['email']
    auth_test_response = slack_bot_client.auth_test()
    team_name = auth_test_response['team']
    team_id = auth_test_response['team_id']

    db = connect_to_mongodb()
    channels_collection = db['channels']
    channel = channels_collection.find_one({'slack_channel_id': channel_id})
    users_collection = db['users']
    user = users_collection.find_one({'user_email': user_email})

    if channel_sub_type == "channel_leave" and user:
        print("str(user['_id']): ", str(user['_id']))
        update_result = channels_collection.update_many(
            {"member_ids": str(user['_id'])},
            {"$pull": {"member_ids": str(user['_id'])}}
        )
        result = users_collection.delete_one({'user_email': user_email})
        print(f"User {user_email} left channel {channel_id}")
        return
    elif user is None and channel_sub_type == "channel_join":
        db_user_id = add_users(db, [user_email], slack_user_id, team_id, team_name, False, channel['company_id'])
        print(f"User {user_email} joined channel {channel_id}")
    else:
        db_user_id = str(user['_id'])

    channels_collection.update_one(
        {"_id": channel['_id']},
        {"$addToSet": {"member_ids": db_user_id}}
    )
    users_collection.update_one(
        {"user_email": user_email},
        {"$set": {"company_id": channel['company_id']}}
    )


@app.route('/ask-casper', methods=['POST'])
def ask_casper():
    slack_client = WebClient(token=os.getenv("SLACK_BOT_TOKEN"))
    data = request.form
    slack_user_id = data.get('user_id')
    slack_channel_id = data.get('channel_id')
    slack_channel_name = data.get('channel_name')
    text = data.get('text')
    query = [{"role": "system",
              "content": "Your name is Casper. An incredibly intelligent, knowledgeable and quick-thinking AI, "
                         "that always replies with professionalism. Only respond based on the context I give you and "
                         "nothing outside that context. Also there can be"
                         "history associated with it so please use that."},
             {"role": "user", "content": text}]

    user_info = slack_client.users_info(user=slack_user_id)
    user_email = user_info['user']['profile']['email']
    user_name = user_info['user']['name']
    channel_name = remove_ask_prefix(slack_channel_name)

    payload = {
        "channel_id": slack_channel_id,
        "user_id": slack_user_id,
        "user_email": user_email,
        "channel_name": channel_name,
        "query": query
    }
    chat_url = 'https://chatservice-2imgap5w2q-uc.a.run.app/chat'
    session = FuturesSession()
    session.post(chat_url, json=payload)

    response_message = f"{user_name}: {text}"
    slack_response = slack_client.chat_postEphemeral(
        channel=slack_channel_id,
        text=response_message,
        user=slack_user_id
    )

    return Response(), 200


@app.route('/chat', methods=['POST'])
def chat():
    data = flask.request.get_json()
    user_id = data.get('user_id')
    channel_id = data.get('channel_id')
    user_email = data.get('user_email')
    channel_name = data.get('channel_name')
    query = data.get('query')
    index_name = fetch_index_name(user_email, channel_name)
    retriever = get_retriever(index_name)
    vectorstore = get_vectorestore(index_name)
    last_item = query[-1]
    # Extract and remove the last element with role="user" as question
    if last_item['role'] == 'user':
        question = last_item['content']
        query.pop()  # Remove the last item from the list
    else:
        question = None
    history = query
    # Combine the current question with the history to provide context
    full_query = f"{question} {history}"
    history_aware_retriever = lambda query: (retriever.get_relevant_documents(full_query, limit=5), history)
    chain_multimodal_rag = multi_modal_rag_chain(history_aware_retriever)
    response = chain_multimodal_rag.invoke({
        "question": question,
        "history": history
    })

    # Send the final result to the user
    slack_client = WebClient(token=os.getenv("SLACK_BOT_TOKEN"))
    response_message = f"Casper: {response}"

    slack_response = slack_client.chat_postEphemeral(
        channel=channel_id,
        text=response_message,
        user=user_id
    )

    return Response(), 200


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
