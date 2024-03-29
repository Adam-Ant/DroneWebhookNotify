#!/usr/bin/python3

# I know I should be using f-strings, but this codebase predates them and it works fine so ¯\_( ツ )_/¯
# pylint: disable=consider-using-f-string

from bottle import run, post, request
from sys import argv
from html import escape
import datetime
import json
import configparser
import requests
import sys


def getDate():
    return datetime.datetime.now().strftime("%c")


def calcTime(start, end):
    minutes, seconds = divmod((int(end) - int(start)), 60)
    datestr = "{:02}m{:02}s".format(minutes, seconds)
    return datestr


def sendTelegramMsg(chatid, message):

    postdata = {
        "parse_mode": "html",
        "disable_web_page_preview": "true",
        "chat_id": chatid,
        "text": message,
    }

    try:
        r = requests.post(
            "https://api.telegram.org/bot{}/sendmessage".format(ttoken),
            json=postdata,
            timeout=10,
        )
        r.raise_for_status()

    except requests.exceptions.HTTPError as err:
        print("[{}] - Error: {}".format(getDate(), err))
        print(
            "[{}] - Failed to send notification for {}".format(
                getDate(), json.dumps(postdata)
            )
        )

    except Exception:
        print("[{}] - Error: Failed to send Telegram notification!".format(getDate()))


def doNotify(success, build):

    status = "SUCCESS" if success else "FAILURE"

    isPR = ""
    if build["build"]["event"] == "pull_request":
        # This isn't pretty, but it works.
        isPR = "#{PR_Num} → ".format(PR_Num=escape(build["build"]["ref"].split("/")[2]))

    multi_stage = ""

    emojiDict = {
        "success": "✅",
        "failure": "❌",
        "running": "▶️",
        "skipped": "🚫",
        "pending": "🔄",
    }

    if len(build["build"]["stages"]) > 1:
        for stage in build["build"]["stages"]:
            multi_stage += (
                "• {stage_name}     <b>{stage_state}</b> in {time} {emoji}\n".format(
                    stage_name=escape(stage["name"]),
                    stage_state=escape(stage["status"]),
                    time=calcTime(stage["started"], stage["stopped"]),
                    emoji=emojiDict.get(stage["status"], "❔"),
                )
            )
        multi_stage += "\n"

    drone_link = "{}/{}/{}".format(
        build["system"]["link"], build["repo"]["slug"], build["build"]["number"]
    )

    try:
        commit_firstline, commit_rest = build["build"]["message"].split("\n", 1)
        commit_rest = "-----\n" + commit_rest.strip()
    except ValueError:
        commit_firstline = build["build"]["message"]
        commit_rest = ""

    notifytmpl = (
        "<b>{repo} [{PR}{branch}]</b> #{number}: <b>{status}</b> in {time}\n"
        + "<a href='{drone_link}'>{drone_link}</a>\n"
        + "{multi_stage}<a href='{git_link}'>#{commit:7.7}</a> ({committer}): <i>{commit_firstline}</i>"
        + "\n{commit_rest}"
    )

    notifymsg = notifytmpl.format(
        PR=isPR,
        branch=escape(build["build"]["target"]),
        commit=escape(build["build"]["after"]),
        commit_firstline=escape(commit_firstline),
        commit_rest=escape(commit_rest),
        committer=escape(build["build"]["author_login"]),
        drone_link=escape(drone_link),
        git_link=escape(build["build"]["link"]),
        multi_stage=multi_stage,
        number=build["build"]["number"],
        repo=escape(build["repo"]["slug"]),
        status=escape(status),
        time=calcTime(build["build"]["started"], build["build"]["finished"]),
    )

    tchat = config["channels"].get(build["repo"]["slug"], default_channel)

    print(
        "[{}] - Sending Telegram notification(s) for {} #{}".format(
            getDate(), build["repo"]["slug"], build["build"]["number"]
        )
    )

    # Send normal telegram notification
    sendTelegramMsg(tchat, notifymsg)

    # If theres a failure channel defined & the build has failed, notify that too
    if (not success) and failure_channel:
        sendTelegramMsg(failure_channel, notifymsg)


@post("/hook")
def webhook():
    json = dict(request.json)
    if json["event"] == "build":
        print(
            "[{}] - {} - Got a webook for {} #{} ({})".format(
                getDate(),
                request.remote_addr,
                json["repo"]["slug"],
                json["build"]["number"],
                json["build"]["status"],
            )
        )

        if json["build"]["status"] == "success":
            doNotify(True, json)
            return "success"

        if json["build"]["status"] == "failure":
            doNotify(False, json)
            return "failure"

    # Default to blackholing it. Om nom nom.
    return "accepted"


if __name__ == "__main__":
    if len(argv) > 1:
        cfg_path = argv[1]
    else:
        cfg_path = "./notify.conf"

    # TODO: Add some sanity checks to make sure the file exists, is readable and contains everything we need.

    config = configparser.ConfigParser()
    config.read(cfg_path)

    ttoken = config["main"]["token"]
    default_channel = config["channels"]["default"]

    # If a failure channel exists, assign it to a var
    failure_channel = False

    if config.has_option("channels", "failure"):
        failure_channel = config["channels"]["failure"]

    if not ttoken:
        print(
            "[{}] - Error: Required variable `main.token' empty or unset".format(
                getDate()
            )
        )
        sys.exit()
    elif not default_channel:
        print(
            "[{}] - Error: Required value `channels.default' empty or unset".format(
                getDate()
            )
        )
        sys.exit()
    print(
        "[{}] - Started Drone Notify. Default Notification Channel: {}".format(
            getDate(), default_channel
        )
    )
    run(host="::", port=5000, quiet=True)
