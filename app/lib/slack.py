import slack
import settings
import os

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
