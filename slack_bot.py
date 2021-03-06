import os
import time

from slackclient import SlackClient

import meetup


# Crop descriptions to the size of (old) Twitter messages.
DESCRITION_LIMIT = 140  # Characters.


class SlackBot(object):
    """Chatbot to interact with the user through Slack."""

    def __init__(self):
        """Initialize a new SlackBot object."""
        # Take token from environment and initialize client.
        slack_token = os.environ['SLACK_BOT_TOKEN']
        self.slack = SlackClient(slack_token)
        self.bot_id = self._get_bot_id()

    def _get_bot_id(self, bot_name='meetup_chatbot'):
        api_call = self.slack.api_call('users.list')
        if api_call.get('ok'):
            # Get all users so we can find our bot.
            users = api_call.get('members')

            # Exit when the meetup bot is not amongst the users.
            if not users:
                print("Could not find bot user with the name " + bot_name)
                return

            for user in users:
                if 'name' in user and user.get('name') == bot_name:
                    bot_id = user.get('id')
                    print("Bot ID for '%s' is %s." % (user['name'], bot_id))
                    return bot_id
        else:
            print("Could not find bot user with the name " + bot_name)

    def connect(self):
        """Connect to Slack and return True if successfull or False if not."""
        return self.slack.rtm_connect()

    def handle_command(self, command, channel):
        """Handle incoming text messages from the user."""
        lowered_command = command.lower()
        if lowered_command.startswith('find '):
            find_position = len('find ')
            groups_text_position = lowered_command.find(' groups ')
            meetups_text_position = lowered_command.find(' meetups ')
            country_name_position = lowered_command.find(' in ')

            if country_name_position < 0:
                country = None
            else:
                country = lowered_command[country_name_position:]

            if groups_text_position < 0:
                if meetups_text_position < 0:
                    text = None
                else:
                    self.post_message(channel, "Let me see what I can find...")

                    text = lowered_command[find_position:meetups_text_position]
                    groups = meetup.find_groups(country, text)
                    meetups = []
                    for g in groups:
                        new_meetups = meetup.get_upcoming_meetups_for_group(
                            g['urlname']
                        )
                        if new_meetups:
                            meetups.extend(new_meetups)

                    # Sort meetups by date.
                    meetups = sorted(meetups, key=lambda m: m['time'])

                    message_text = 'I found you the following meetups:'
                    attachments = []
                    for m in meetups:
                        attachments.append({
                            'title': m['name'],
                            'title_link': m['event_url'],
                            # Crop too long descriptions.
                            'text': m['description'][:DESCRITION_LIMIT],
                            # Convert timestamp to Unix time.
                            'ts': m['time'] / 1000})
                    # Add attachment for 'show more' button
                    attachments.append({
                        'fallback': 'You are unable to choose a game',
                        'callback_id': 'find_more',
                        'attachment_type': 'default',
                        'actions': [{
                            'name': 'more',
                            'text': 'Find more',
                            'type': 'button',
                            'value': 'more'
                            }]
                        })
                    self.post_message(channel, message_text, attachments)

            else:
                text = lowered_command[find_position:groups_text_position]

                groups = meetup.find_groups(country, text)

                message_text = 'I found you the following meetup groups:'
                attachments = []
                for g in groups:
                    attachments.append({'title': g['name'],
                                        'title_link': g['link']})
                self.post_message(channel, message_text, attachments)

    def post_message(self, channel, text, attachments=None):
        """Use the chatbot to post a message text to the given channel."""
        self.slack.api_call(
            "chat.postMessage",
            channel=channel,
            text=text,
            attachments=attachments,
            as_user=True
        )

    def _parse_slack_output(self, slack_rtm_output):
        """Parse a badge of new messages."""
        output_list = slack_rtm_output
        if output_list and len(output_list) > 0:
            for output in output_list:
                if output and 'text' in output:
                    # Avoid feedback loops triggered by bot messages.
                    if 'user' in output and output['user'] != self.bot_id:
                        return (output['text'].strip(), output['channel'])
        return None, None

    def read_and_parse(self):
        """Read and parse new events from the Slack Real Time Messaging API."""
        return self._parse_slack_output(self.slack.rtm_read())


if __name__ == "__main__":
    # Set delay between checking messages from the firehose.
    READ_WEBSOCKET_DELAY = 0.2

    bot = SlackBot()

    if bot.connect():
        print("Slack Bot connected and running!")

        while True:
            try:
                command, channel = bot.read_and_parse()
                if command and channel:
                    bot.handle_command(command, channel)

                time.sleep(READ_WEBSOCKET_DELAY)
            except KeyboardInterrupt:
                print("\rBot shut down by user")
                break
    else:
        print("Connection failed. Invalid Slack token or bot ID?")
