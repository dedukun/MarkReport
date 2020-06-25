#!/usr/bin/env python3

# Command line flags

import os
import glob
import re
import pyinotify
import subprocess
from sys import stdout, stderr
from time import time, sleep
from tempfile import gettempdir
from distutils.dir_util import copy_tree
from shutil import copyfile
from weasyprint import HTML
import argparse

parser = argparse.ArgumentParser(
    description='Converts Markdown to elegant PDF reports')
parser.add_argument('--basic', dest='basic', action='store_true',
                    help='Do not enrich HTML with LaTeX and syntax highlighting (faster builds)')
parser.add_argument('--watch', dest='watch', action='store_true',
                    help='Watch the current folder for changes and rebuild automatically')
parser.add_argument('--quiet', dest='quiet', action='store_true',
                    help='Do not output any information')
parser.add_argument("--timeout", type=int, default=2,
                    help='Page generation timeout')
parser.add_argument("--base-html", type=str, default="",
                    help='The path to the base HTML file')
parser.set_defaults(watch=False)
args = parser.parse_args()


# Check directory

ok = False
for file in os.listdir("."):
    if file.endswith(".md"):
        ok = True
        break
if not ok:
    stderr.write("No markdown file found in the current folder")
    exit(1)

if args.base_html != "":
    if not os.path.isfile(args.base_html):
        stderr.write("The given base HTML file doesn't exist")
        exit(1)

script_path = os.path.dirname(os.path.realpath(__file__))

# Temp dir

timestamp = str(int(time()))
tmp_dir = gettempdir() + "/" + timestamp + "_md-report/"
os.makedirs(tmp_dir, exist_ok=True)

# Headless browser

if not args.basic:
    from selenium import webdriver
    from selenium.webdriver.firefox.options import Options
    from selenium.webdriver.common.desired_capabilities import DesiredCapabilities

    options = Options()
    options.headless = True
    options.log.level = "trace"

    d = DesiredCapabilities.FIREFOX
    d['loggingPrefs'] = {'browser': 'ALL'}

    driver = webdriver.Firefox(options=options, capabilities=d)
    driver.set_page_load_timeout(args.timeout)

prev_compile_time = 0


def recompile(notifier):
    if notifier is not None and (notifier.maskname != "IN_MODIFY" or notifier.pathname.endswith(".pdf")):
        return
    global prev_compile_time
    if time() - prev_compile_time < 1:
        return
    prev_compile_time = time()

    if not args.quiet:
        stdout.write("\rBuilding the PDF file...")
        stdout.flush()

    files = glob.glob(tmp_dir + '/*.md')
    for f in files:
        os.remove(f)

    if args.base_html == "":
        copyfile(script_path + "/base.html", tmp_dir + "/base.html")
    else:
        copyfile(args.base_html, tmp_dir + "/base.html")
    if not os.path.islink(tmp_dir + "/src"):
        os.symlink(script_path + "/src", tmp_dir + "/src")
    copy_tree(".", tmp_dir)

    # Markdown parsing

    subprocess.check_output(script_path + "/md-parsing " +
                            tmp_dir, shell=True).decode('utf-8')
    html_file_name = tmp_dir + "output.html"

    # Interpret JS code

    if not args.basic:
        driver.get("file:///" + html_file_name)
        sleep(2)
        elem = driver.find_element_by_xpath("//*")
        interpreted_html = elem.get_attribute("outerHTML")

        with open(html_file_name, "w") as html_out_file:
            html_out_file.write(interpreted_html)

    # Create final PDF file

    pdf = HTML(html_file_name).write_pdf()
    f = open("output.pdf", 'wb')
    f.write(pdf)

    if not args.quiet:
        stdout.write("\rDone.                   ")
        stdout.flush()


recompile(None)

if not args.watch:
    if not args.basic:
        driver.quit()
    exit(0)

watch_manager = pyinotify.WatchManager()
event_notifier = pyinotify.Notifier(watch_manager, recompile)

watch_manager.add_watch(os.path.abspath("."), pyinotify.ALL_EVENTS, rec=True)
event_notifier.loop()

if not args.basic:
    driver.quit()
