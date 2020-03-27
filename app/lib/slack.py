import logging
import slack
import settings
import os
import traceback

def post_slack_message(message, channel=None, **kwargs):
    if channel is None:
        channel = os.getenv("SLACK_CHANNEL")

    slack_token = os.getenv("SLACK_TOKEN")

    sc = slack.WebClient(token=slack_token)

    r = sc.chat_postMessage(
        channel=channel,
        text=message,
        as_user=True,
        **kwargs, #e.g. attachments
    )

    # if 'error' in r:
    #     raise slack.errors.SlackClientError("%s: %s" % (r['error'], channel))

    return r


def slack_link(url, text=""):
    """
    Return a slack-formatted URL of <path|text>.
    """
    if text:
        return "<%s|%s>" % (url, text)

    else:
        return "<%s>" % url


def new_file_slack_message(message, file_path, duration):
    # post a link to a folder/file with an SMB mount.
    if file_path.startswith(settings.MASTER_FOLDER):
        url = file_path.replace(settings.MASTER_FOLDER, settings.MASTER_URL)
    elif file_path.startswith(settings.ACCESS_FOLDER):
        url = file_path.replace(settings.ACCESS_FOLDER, settings.ACCESS_URL)
    elif file_path.startswith(settings.WEB_FOLDER):
        url = file_path.replace(settings.WEB_FOLDER, settings.WEB_URL)
    else:
        raise ValueError("%s doesn't seem to be in either the Master, Access or Web folders. Not sure how to make a URL for this." % file_path)

    dirname = os.path.dirname(url)
    attachments = [
        {
            "fallback": "Open folder at %s" % dirname,
            "actions": [
                {
                    "type": "button",
                    "text": "View file :cinema:",
                    "url": url,
                    "style": "primary" # or danger
                },
                {
                    "type": "button",
                    "text": "Open folder :open_file_folder:",
                    "url": dirname,
                },
            ]
        }
    ]

    formatted_message = "%s: %s (Duration %s)" % (message, os.path.basename(url), duration)
    post_slack_message(formatted_message, attachments=attachments)


def post_slack_exception(message):
    traceback.print_exc()
    post_slack_message(message)
