#!/usr/bin/env python
#
# main.py for Ship-It - must be run as root
#

import datetime
import os
import signal
import subprocess
import sys
import RPi.GPIO as GPIO
from threading import Thread
from time import sleep

TEAMCITY_URL = "cm-build.criticalmass.com"
TEAMCITY_USER = os.environ.get("SHIP_IT_TEAMCITY_USER")
TEAMCITY_PASS = os.environ.get("SHIP_IT_TEAMCITY_PASS")

# Some builds we know about and have access to
builds = {
    "bt280": {"name": "Client  Int"},
##    " bt390": {"name": "Client  QA"},
##    "bt443": {"name": "Client Approval"},
##    "bt398": {"name": "Client Stage"},
    "bt1568": {"name": "Hubot"}
    }

# GPIO pins (BCM numbering)
blinker = 17
armingSwitch = 24
launchButton = 27
branchButton = 23
# the number of LEDs must match the number of builds
branchA_LED = 22
branchB_LED = 25

branchLEDs = [branchA_LED, branchB_LED]
targetBranch = builds.items()[0][0]

def blink(pin):
    "one blink cycle ending with the LED off"
    GPIO.output(pin,GPIO.HIGH)
    sleep(.1)
    GPIO.output(pin,GPIO.LOW)
    sleep(.1)
    return

def alt_blink(pin):
    "2 second blink cycle ending with the LED on"
    for i in range(0, 20):
        GPIO.output(pin,GPIO.LOW)
        sleep(.1)
        GPIO.output(pin,GPIO.HIGH)
        sleep(.1)
    return

def switch_target(target):
    "switch to the next "
    global targetBranch
    print("[" + get_now() + "] Changing target... was " + builds[target]["name"] + ","),
    currItemIndex = builds.keys().index(target)
    nextItemIndex = (currItemIndex + 1) % len(builds)
    targetBranch = builds.items()[nextItemIndex][0]
    GPIO.output(branchLEDs[currItemIndex], GPIO.LOW)
    GPIO.output(branchLEDs[nextItemIndex], GPIO.HIGH)
    print("is " + builds[targetBranch]["name"])
    sleep(0.2)

def run_a_build(target):
    "post a build request to teamcity for the currently specified target -- and blink some LEDs!"
    GPIO.output(blinker, GPIO.HIGH)
    thread = Thread(target=play_audio, args=("alarm.ogg",), verbose=False)
    thread.start()
    currItemIndex = builds.keys().index(target)
    print("[" + get_now() + "] Triggered a build of " + builds[target]["name"])
    # some necessarily println debugging for now
    cmd = "curl -v -u {}:{} http://{}/app/rest/buildQueue -X POST -H 'Content-Type:application/xml' -d '{}'".format(TEAMCITY_USER, TEAMCITY_PASS, TEAMCITY_URL, get_tc_build_xml(target))
    print("[" + get_now() + "] " + cmd)
    ret = os.system(cmd)
    print("[" + get_now() + "] ret: {}.  (should be 0)".format(ret))
    alt_blink(branchLEDs[currItemIndex])
    # assumes alarm.ogg length is 8 seconds
    sleep(8)
    GPIO.output(blinker, GPIO.LOW)

def get_tc_build_xml(build_id):
    "get the teamcity build xml required to trigger a build from the rest api"
    return "<build><buildType id=\"" + build_id + "\"/><comment><text>triggered by ship-it</text></comment></build>"

def get_now():
    "get the current date and time as a string"
    return datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

def play_audio(f):
    """Use omxplayer to play the specified audio file.
    The input is checked against a list of files to prevent malicious or
    unintended consequences of running the subprocess in the default shell.
    """
    if f in ['alarm.ogg', 'bzz.ogg']:
        cmd = "omxplayer -o local /home/pi/ship-it/{}".format(f)
        print("[" + get_now() + "] about to run " + cmd)
        subprocess.call(cmd, shell=True, stderr=subprocess.STDOUT)
    else:
        print("[" + get_now() + "] {} is an unrecognized audio file".format(f))

def init_pins():
    "setup all the GPIO for ship-it"
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(launchButton, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    GPIO.setup(armingSwitch, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    GPIO.setup(blinker, GPIO.OUT)
    GPIO.setup(branchButton, GPIO.IN)
    for pin in branchLEDs:
        GPIO.setup(pin, GPIO.OUT)
        GPIO.output(pin, GPIO.LOW)

    # by default target the first branch
    GPIO.output(branchLEDs[0], GPIO.HIGH)
    print("[" + get_now() + "] pins have been initialized!")

def cleanup_pins():
    "cleanup everything we created with the GPIO"
    print("[" + get_now() + "] cleaning up pins!")
    GPIO.cleanup()

def sigterm_handler(_signo, _stack_frame):
    "When sysvinit sends the TERM signal, cleanup before exiting."
    print("[" + get_now() + "] received signal {}, exiting...".format(_signo))
    cleanup_pins()
    sys.exit(0)

signal.signal(signal.SIGTERM, sigterm_handler)

if __name__ == "__main__":
    """init some pins and run the loop"""
    init_pins()

    try:
        while True:
            launchButtonState = GPIO.input(launchButton)
            branchButtonState = GPIO.input(branchButton)

            if GPIO.input(armingSwitch) == True:
                armed = True
                blink(blinker)
            else:
                armed = False

            # target switching
            if branchButtonState == 0:
                switch_target(targetBranch)

            # launch button handling
            if armed == True:
                if launchButtonState == 0:
                    run_a_build(targetBranch)
                    sleep(0.5)
            sleep(0.2)

    except KeyboardInterrupt:
        cleanup_pins()
