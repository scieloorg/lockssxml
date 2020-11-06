# coding: utf-8
import configparser
import datetime
import os
import sys
import re
import unicodedata

from xylose.scielodocument import Issue

from lxml.etree import Element
from lxml import etree
import logging
import requests


# Check and create logs directory
if not os.path.exists('logs'):
    os.mkdir('logs')

logging.basicConfig(filename='logs/lockssxml.info.txt', level=logging.INFO)
logger = logging.getLogger(__name__)

# Format ISO date
dateiso = datetime.datetime.now().strftime('%Y%m%d')

# Read config
config = configparser.ConfigParser()
config.read('config.ini')

# Host and base path to Articlemeta API
host = config['articlemeta']['host']

# Collection acronym
col = config['articlemeta']['col']


def accent_remover(text):
    # Unicode normalize turns a character into its Latin equivalent
    norm = unicodedata.normalize('NFKD', text)

    # Remakes a string whitout accents
    text_norm = u''.join([c for c in norm if not unicodedata.combining(c)])

    # Regex to returns only Alpha and Numbers characters
    return re.sub('[^a-zA-Z0-9]', '', text_norm)


def request_issue(ipid):
    # Request issues
    jsondocs = {}
    try:
        url = ('%sissue/?collection=%s&code=%s' % (host, col, ipid))
        # print(url)
        logger.info(url)
        r = requests.get(url)
        if r.status_code == 200:
            jsondocs = r.json()
            r.close()
    except requests.ConnectionError as e:
        msg = ('request_error|status_code:%s|pid:%s|erro:%s' % (r.status_code, ipid, e))
        logger.info(msg)
        print(msg)
        jsondocs = {}

    return jsondocs


def json2xml(ipidlist):
    # lockss-config elements
    lockss_config = Element('lockss-config')

    org_lockss_titleset = Element('property', name="org.lockss.titleSet")
    lockss_config.append(org_lockss_titleset)

    publisher = Element('property', name="SciELO")
    org_lockss_titleset.append(publisher)

    name = Element('property', name="name", value='All SciELO AUs')
    publisher.append(name)

    class_name = Element('property', name="class", value="xpath")
    publisher.append(class_name)

    xpath = Element('property', name="xpath", value='[attributes/publisher="SciELO"]')
    publisher.append(xpath)

    # org.lockss.title
    org_lockss_title = Element('property', name='org.lockss.title')
    lockss_config.append(org_lockss_title)

    # Issue Iteration
    vol_ini = None
    ijson = {}
    for ipid in ipidlist:
        try:
            ijson = request_issue(ipid)
            if ijson:
                # Xylose
                issue = Issue(ijson)

                if issue.volume != vol_ini:
                    vol_ini = issue.volume
                    print('issn: %s volume: %s' % (issue.journal.scielo_issn, issue.volume,))

                    # concatenated title
                    if hasattr(issue.journal, 'title'):
                        title = issue.journal.title
                        titleconc = accent_remover(issue.journal.title)

                    # volume number
                    if hasattr(issue, 'volume'):
                        volume = issue.volume

                    # SciELO Plugin
                    if title and volume:
                        scieloplugin = Element('property', name="SciELOPlugin%s%s" % (titleconc, volume))
                        org_lockss_title.append(scieloplugin)

                    # attributes publisher
                    attributes_publisher = Element('property', name="attributes.publisher", value="SciELO")
                    scieloplugin.append(attributes_publisher)

                    # journal title
                    if hasattr(issue.journal, 'acronym') and title:
                        acronym = issue.journal.acronym
                        journal_title = Element('property', name='journalTitle', value='%s-%s' % (acronym.upper(), title))
                        scieloplugin.append(journal_title)

                    # ISSN
                    if hasattr(issue.journal, 'scielo_issn'):
                        issn = Element('property', name="issn", value=issue.journal.scielo_issn)
                        scieloplugin.append(issn)
                    # Electronic issn
                    if hasattr(issue.journal, 'electronic_issn'):
                        eissn = Element('property', name="eissn", value=issue.journal.electronic_issn)
                        scieloplugin.append(eissn)

                    # type
                    type = Element('property', name="type", value="journal")
                    scieloplugin.append(type)

                    # title
                    title_element = Element('property', name="title", value='%s-%s Volume %s' % (acronym.upper(), title, volume))
                    scieloplugin.append(title_element)

                    plugin = Element('property', name="plugin", value='org.lockss.plugin.scielo.ClockssSciELOPlugin')
                    scieloplugin.append(plugin)

                    # Param1
                    param1 = Element('property', name='param.1')
                    scieloplugin.append(param1)
                    key1 = Element('property', name='key', value='base_url')
                    param1.append(key1)
                    value1 = Element('property', name='value', value=config['params']['base_url'])
                    param1.append(value1)

                    # Param2
                    param2 = Element('property', name='param.2')
                    scieloplugin.append(param2)
                    key2 = Element('property', name="key", value="journal_issn")
                    param2.append(key2)
                    value2 = Element('property', name='value', value=issue.journal.scielo_issn)
                    param2.append(value2)

                    # Param3
                    param3 = Element('property', name='param.3')
                    scieloplugin.append(param3)
                    key3 = Element('property', name="key", value="year")
                    param3.append(key3)
                    value3 = Element('property', name='value', value=issue.publisher_id[9:13])
                    param3.append(value3)
                else:
                    continue
        except Exception as e:
            print(e)
            logger.info(e)
            continue

    # Generates the XML
    return etree.tostring(lockss_config,
                          pretty_print=True,
                          xml_declaration=False,
                          encoding='utf-8')


def main():
    # Folder and file names
    if config['paths']['pidlistname'] == '':
        print('pidlistname=empty.\nEnter the PID list name in config.ini.')
        sys.exit()

    xmlfilename = config['paths']['xmlfilename']

    xmlfolder = config['paths']['xmlfoldername']

    if config['paths']['prefix'] == 'yes':
        if config['paths']['xmlfilename'] == '':
            xmlfilename = dateiso
        else:
            xmlfilename = ('%s_%s' % (dateiso, xmlfilename))

    if config['paths']['prefix'] == 'no':
        if config['paths']['xmlfilename'] == '':
            print('xmlfilename = empty.\nEnter a name in config.ini.')
            exit()

    if config['paths']['prefix'] == '':
        if config['paths']['xmlfilename'] == '':
            print('xmlfilename = empty.\nEnter a name in config.ini.')
            exit()

    xmlout = ('%s/%s.xml' % (xmlfolder, xmlfilename))

    print('\nfolder/xmlfile: %s\n' % xmlout)

    # Issue PID List
    with open(config['paths']['pidlistname']) as f:
        pidlist = [line.strip()[1:18] for line in f]
        # Distinct Issue List
        ipidlist = sorted(list(set(pidlist)), reverse=True)
    f.close()

    # Build XML object
    xmldocs = json2xml(ipidlist=ipidlist)

    # Check and create xml folder output
    if xmldocs:
        if not os.path.exists(xmlfolder):
            os.mkdir(xmlfolder)

        # Write the XML file in folder
        with open(xmlout, encoding='utf-8-sig', mode='w') as f:
            # Declaration with quotation marks
            f.write(u'<?xml version="1.0" encoding="UTF-8"?>\n')
            f.write(xmldocs.decode('utf-8'))
        f.close()

if __name__ == "__main__":
    main()
