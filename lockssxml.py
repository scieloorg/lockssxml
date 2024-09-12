# coding: utf-8
import argparse
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

LOG_FORMAT = '%(asctime)s %(name)s %(levelname)s %(message)s'
LOG_LEVEL = logging.DEBUG

# Check and create logs directory
if not os.path.exists('logs'):
    os.mkdir('logs')

logging.basicConfig(filename='logs/lockssxml.info.txt', level=logging.INFO)
logger = logging.getLogger(__name__)

# Format ISO date
dateiso = datetime.datetime.now().strftime('%Y%m%d')


def accent_remover(text):
    # Unicode normalize turns a character into its Latin equivalent
    norm = unicodedata.normalize('NFKD', text)

    # Remakes a string whitout accents
    text_norm = u''.join([c for c in norm if not unicodedata.combining(c)])

    # Regex to returns only Alpha and Numbers characters
    return re.sub('[^a-zA-Z0-9]', '', text_norm)


def request_issue(host, col, ipid):
    # Request issues
    jsondocs = {}
    url = ('%sissue/?collection=%s&code=%s' % (host, col, ipid))
    logger.info(url)
    r = requests.get(url)
    if r.status_code == 200:
        jsondocs = r.json()
        r.close()
    return jsondocs


def json2xml(host, col, base_url, ipidlist):
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

    xpath = Element('property', name="xpath",
                    value='[attributes/publisher="SciELO"]')
    publisher.append(xpath)

    # org.lockss.title
    org_lockss_title = Element('property', name='org.lockss.title')
    lockss_config.append(org_lockss_title)

    # Issue Iteration
    ijson = {}
    journal_issues = {}
    for ipid in ipidlist:
        try:
            ijson = request_issue(host, col, ipid)
            if ijson:
                # Xylose
                issue = Issue(ijson)

                year = issue.publisher_id[9:13]
                year_issue = (year, issue.volume)

                journal_issues.setdefault(issue.journal.scielo_issn, [])
                journal_current_unity = journal_issues[
                    issue.journal.scielo_issn
                ]

                if year_issue not in journal_current_unity:

                    journal_current_unity.append(year_issue)

                    if not issue.volume:
                        volume = year
                    else:
                        volume = issue.volume

                    print('issn: %s volume: %s' %
                          (issue.journal.scielo_issn, volume))

                    # concatenated title
                    if hasattr(issue.journal, 'title'):
                        title = issue.journal.title
                        titleconc = accent_remover(issue.journal.title)

                    # SciELO Plugin
                    if title and volume:
                        scieloplugin = Element(
                            'property', name="SciELOPlugin%s%s" % (
                                titleconc, volume)
                        )
                        org_lockss_title.append(scieloplugin)

                    # attributes publisher
                    attributes_publisher = Element(
                        'property', name="attributes.publisher", value="SciELO")
                    scieloplugin.append(attributes_publisher)

                    # journal title
                    if hasattr(issue.journal, 'acronym') and title:
                        acronym = issue.journal.acronym
                        journal_title = Element(
                            'property', name='journalTitle', value='%s-%s' % (
                                acronym.upper(), title)
                        )
                        scieloplugin.append(journal_title)

                    # ISSN
                    if hasattr(issue.journal, 'scielo_issn'):
                        issn = Element('property', name="issn",
                                       value=issue.journal.scielo_issn)
                        scieloplugin.append(issn)
                    # Electronic issn
                    check_eissn= getattr(issue.journal, 'electronic_issn')
                    if check_eissn is not None:
                        eissn = Element('property', name="eissn",
                                        value=issue.journal.electronic_issn)
                        scieloplugin.append(eissn)
                    else:
                        eissn = Element('property', name="eissn",
                                        value="")
                        scieloplugin.append(eissn)

                    # type
                    type = Element('property', name="type", value="journal")
                    scieloplugin.append(type)

                    # title
                    title_element = Element(
                        'property', name="title", value='%s-%s Volume %s' % (
                            acronym.upper(), title, volume)
                    )
                    scieloplugin.append(title_element)

                    plugin = Element(
                        'property', name="plugin",
                        value='org.lockss.plugin.scielo.ClockssSciELOPlugin'
                    )
                    scieloplugin.append(plugin)

                    # Param1
                    param1 = Element('property', name='param.1')
                    scieloplugin.append(param1)
                    key1 = Element('property', name='key', value='base_url')
                    param1.append(key1)
                    value1 = Element('property', name='value',
                                     value=base_url)
                    param1.append(value1)

                    # Param2
                    param2 = Element('property', name='param.2')
                    scieloplugin.append(param2)
                    key2 = Element('property', name="key",
                                   value="journal_issn")
                    param2.append(key2)
                    value2 = Element('property', name='value',
                                     value=issue.journal.scielo_issn)
                    param2.append(value2)

                    # Param3
                    param3 = Element('property', name='param.3')
                    scieloplugin.append(param3)
                    key3 = Element('property', name="key", value="year")
                    param3.append(key3)
                    value3 = Element('property', name='value', value=year)
                    param3.append(value3)
                else:
                    continue
        except Exception as e:
            print(e)
            logger.info(e)
            # continue

    # Generates the XML
    return etree.tostring(lockss_config,
                          pretty_print=True,
                          xml_declaration=False,
                          encoding='utf-8')


def json2csv(host, col, ipidlist):
    """
    output: 
            [{'publisher': 'SciELO', 'journal': 'Acta Amazonica',
            'issn': '0044-5967', 'eissn': '1809-4392',
            'in_progress': {'2010': '40', '2011': '41'} }]
    """

    data_list = []

    for ipid in ipidlist:
        data_dict = {}
        flag = False
        try:
            ijson = request_issue(host, col, ipid)
            if ijson:
                # Xylose
                issue = Issue(ijson)
                year = issue.publisher_id[9:13]
                volume = issue.volume if issue.volume else year

                for d_journal in data_list:

                    if d_journal.get('journal') == issue.journal.title:
                        d_journal['in_progress'][year] = volume
                        flag = True

                if not flag:
                    data_dict['publisher'] = issue.journal.publisher_name
                    data_dict['journal'] = issue.journal.title
                    data_dict['issn'] = issue.journal.scielo_issn \
                        if issue.journal.scielo_issn else ""
                    data_dict['eissn'] = issue.journal.electronic_issn \
                        if issue.journal.electronic_issn else ""
                    data_dict.setdefault('in_progress', {})
                    data_dict['in_progress'][year] = volume

                    data_list.append(data_dict)

        except Exception as e:
            print(e)
            # logger.info(e)
            # continue

    return data_list


def main(
        outputdir, outputfile, prefix,
        host, col,
        base_url, output_format, pid_list
):
    # Folder and file names
    # if pidlistname == '':
    #     print('pidlistname=empty.\nEnter the PID list name in config.ini.')
    #     sys.exit()

    if prefix == 'yes':
        if outputfile == '':
            outputfile = dateiso
        else:
            outputfile = ('%s_%s' % (dateiso, outputfile))

    if prefix == 'no':
        if outputfile == '':
            print('outputfile = empty.\nEnter a name in config.ini.')
            exit()

    if prefix == '':
        if outputfile == '':
            print('outputfile = empty.\nEnter a name in config.ini.')
            exit()

    # xmlout = ('%s/%s.xml' % (outputdir, outputfile))

    # print('\nfolder/xmlfile: %s\n' % xmlout)
    # import pdb; pdb.set_trace()
    if output_format == 'xml':

        xmlout = ('%s/%s.xml' % (outputdir, outputfile))

        print('\nfolder/xmlfile: %s\n' % xmlout)

        # Build XML object
        xmldocs = json2xml(host, col, base_url, pid_list)


        # Check and create xml folder output
        if xmldocs:
            if not os.path.exists(outputdir):
                os.mkdir(outputdir)

            # Write the XML file in folder
            with open(xmlout, encoding='utf-8-sig', mode='w') as f:
                # Declaration with quotation marks
                f.write(u'<?xml version="1.0" encoding="UTF-8"?>\n')
                f.write(xmldocs.decode('utf-8'))
            f.close()

    elif output_format == 'csv':
        # Build CSV object
        list_journal = json2csv(host, col, pidlist)
        with open('out.csv', mode='w') as f:
            f.write(
                "%s; %s; %s; %s; %s; %s; %s; %s\n" % (
                    "Publisher",
                    "Title", "ISSN", "eISSN", "Preserved Volumes",
                    "Preserved Years", "In Progress Volumes",
                    "In Progress Years")
            )
            for journal in list_journal:
                f.write(
                    "%s; %s; %s; %s; %s; %s; %s; %s\n" % (
                        "SciELO",
                        # ",".join(journal.get("publisher")),
                        journal.get("journal"),
                        journal.get("issn"),
                        journal.get("eissn"),
                        "", "",
                        ", ".join(journal.get("in_progress").values()),
                        ", ".join(journal.get("in_progress").keys()))
                )
    else:
        print("Format not accept!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '-pidfile', help='File name of list of sbid for generate XMLs or CVS [required]',
        default='pids.txt'
    )
    parser.add_argument(
        '-outputdir', help='Folder name for save output generated file [required]',
        default='output'
    )
    parser.add_argument(
        '-outputfile', help='Give it a name for your generated file.',
        default='titledb'
    )
    parser.add_argument(
        '-prefix', help='To prefix file name with date iso format (yes/no) [required]',
        default='yes'
    )
    parser.add_argument(
        '-host', help='Host of SciELO Articlemeta API[required]',
        default='http://articlemeta.scielo.org/api/v1/'
    )
    parser.add_argument(
        '-col', help='Collection acronym name',
        default='scl'
    )
    parser.add_argument(
        '-base_url', help='URL used by LOCKSS to harvest',
        default='http://www.scielo.br/'
    )
    parser.add_argument(
        '-output_format', help='Output format file',
        default='xml'
    )
    parser.add_argument(
        '-o', dest='output', type=argparse.FileType('a'),
        help='Output File', default=sys.stdout
    )
    parser.add_argument(
        '-l', dest='log', type=str,
        help='Log File', default=None
    )
    args = parser.parse_args()
    if args.log:
        logging.basicConfig(format=LOG_FORMAT, filename=args.log,
                            level=LOG_LEVEL)
    else:
        logging.basicConfig(format=LOG_FORMAT, level=LOG_LEVEL)
    try:
        # Issue PID List
        with open(args.pidfile) as f:
            pidlist = [line.strip()[1:18] for line in f]
            # Distinct Issue List
            pid_list = sorted(list(set(pidlist)), reverse=True)
        f.close()

        main(args.outputdir, args.outputfile,
             args.prefix, args.host,
             args.col, args.base_url, args.output_format, pid_list
             )
    except Exception as exc:
        logging.exception("Error running task")
        exit(1)



