#!/usr/bin/python

import sys
import logging
import json
import math
import requests
import random
import string
import ConfigParser
import sys
import traceback
import datetime
from time import sleep

requests.packages.urllib3.disable_warnings()

# setup logging to print timestamps
logging.basicConfig(format='[%(asctime)s %(levelname)s] %(message)s')

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

DEFAULT_CONFIG_FILE = "config.ini"
DEFAULT_CONFIG_LIST_JSON = 'sampleBuildConfigs/dependantProjects.json'

configFile = DEFAULT_CONFIG_FILE
if len(sys.argv) > 1:
    configFile = sys.argv[1]

configListJson = DEFAULT_CONFIG_LIST_JSON
if len(sys.argv) > 2:
    configListJson = sys.argv[1]

buildConfigIds = []
recordIds = []
buildTimes = []
statuses = []
RETRIES = 6

def get(rest_point, params = {}, headers = {}):
    return request_with_retry(requests.get, rest_point, params, headers)

def post(rest_point, params = {}, headers = {}):
    return request_with_retry(requests.post, rest_point, params, headers)

def request_with_retry(request_type, rest_point, params, headers):
    for i in range(RETRIES):
        try:
            response = request_type(rest_point, data=params, headers=headers, verify=False)
            json_content = json.loads(response.content)
            return response
        except Exception:
            traceback.print_exc(file=sys.stdout)
        logger.warn("Retrying in 10 seconds...")
        sleep(10)

    logger.error("Retries exceeded! Could not get valid response.")
    sys.exit(1)


def load(value):
    parser = ConfigParser.ConfigParser()
    parser.read(configFile)
    return parser.get("CREDENTIALS", value)

# Note: when using it for actual requests, add to header: 'Authorization: Bearer <token>'
def getToken(username, password, realm, client_id, keycloak_url):
    params = {'grant_type': 'password',
              'client_id': client_id,
              'username': username,
              'password': password}
    response =  post(keycloak_url + "/auth/realms/" + realm + "/tokens/grants/access", params)

    if response.status_code == 200:
        token = json.loads(response.content)['access_token']
        return token

    logger.error("Could not get keycloak token")
    return None

def getHeaders():

    token = getToken(USERNAME, PASSWORD, REALM, CLIENT_ID, KEYCLOAK_URL)
    return {'content-type': 'application/json', "Authorization": "Bearer " + token}

def getId(data):
    idKey = unicode("id", "utf-8")
    contentKey = unicode("content", "utf-8")

    return data[contentKey][idKey]

def fireBuilds(idList):
    for i in idList:
        logger.info("Firing build %s", i)
        r = post(SERVER_NAME + "/pnc-rest/rest/build-configurations/" + str(i) + "/build", headers = getHeaders())
        logger.info("Fired build %s", i)
        jsonContent = json.loads(r.content)
        recordId = getId(jsonContent)
        recordIds.append(recordId)
        sleep(2)

def waitTillBuildsAreDone():
    logger.info("Builds are running...")
    while True:
        if not buildsAreRunning():
            break
        sleep(5)
    logger.info("Builds are done!")

def buildsAreRunning():
    for i in recordIds:
            r = get(SERVER_NAME + "/pnc-rest/rest/running-build-records/" + str(i), headers=getHeaders())
            if r.status_code == 200:
                return True
    return False

def getAllBuildTimes():
    for i in recordIds:
        time = int(getTime(i)) / 1000
        buildTimes.append(time)

def printStartStopTimes():
    print('')
    for buildId in recordIds:
        r = get(SERVER_NAME + "/pnc-rest/rest/build-records/" + str(buildId), headers=getHeaders())
        content = json.loads(r.content)

        contentKey = unicode("content", "utf-8")
        startTimeKey = unicode("startTime", "utf-8")
        endTimeKey = unicode("endTime", "utf-8")

        startTime = int(content[contentKey][startTimeKey])
        endTime = int(content[contentKey][endTimeKey])
        duration = (endTime - startTime)/1000

        startTimeStr = datetime.datetime.fromtimestamp(startTime/1000).strftime('%H:%M:%S')
        endTimeStr = datetime.datetime.fromtimestamp(endTime/1000).strftime('%H:%M:%S')

        logger.info("Build Record: %s :: Start Time: %s :: End Time: %s :: Duration: %s seconds",
                    buildId, startTimeStr, endTimeStr, duration)

    print('')


def getTime(buildId):
    r = get(SERVER_NAME + "/pnc-rest/rest/build-records/" + str(buildId), headers=getHeaders())
    content = json.loads(r.content)

    contentKey = unicode("content", "utf-8")
    startTimeKey = unicode("startTime", "utf-8")
    endTimeKey = unicode("endTime", "utf-8")

    return  int(content[contentKey][endTimeKey]) - int(content[contentKey][startTimeKey])

def getStatuses():
    for i in recordIds:
        statuses.append(getStatus(i))

def getStatus(recordId):
    r = get(SERVER_NAME + "/pnc-rest/rest/build-records/" + str(recordId), headers=getHeaders())
    content = json.loads(r.content)

    contentKey = unicode("content", "utf-8")
    statusKey = unicode("status", "utf-8")

    return content[contentKey][statusKey]

def randomName(size=6, chars=string.ascii_uppercase + string.digits + string.ascii_lowercase):
    return ''.join(random.choice(chars) for i in range(size))


def calculate_standard_deviation(list_of_items):
    n = len(list_of_items)

    # if only 1 item
    if n == 1:
        return 0

    mean = float(sum(list_of_items)) / n

    sum_val = 0
    for item in list_of_items:
        sum_val += math.pow(item - mean, 2)

    std_dev = math.sqrt(float(sum_val) / (n - 1))
    return std_dev

def calculate_standard_error(list_of_items):
    std_dev = calculate_standard_deviation(list_of_items)
    return std_dev / math.sqrt(len(list_of_items))

def num_successes():
    return len(filter(lambda x: x == "SUCCESS", statuses))

def num_failures():
    return len(filter(lambda x: x != "SUCCESS", statuses))

def average_build_times():
    return sum(buildTimes)/len(buildTimes)

def printStats():
    logger.info("#####STATS#####")
    logger.info("Number of successes: %s", num_successes())
    logger.info("Number of failures: %s", num_failures())
    logger.info("The build times are: %s seconds", buildTimes)
    logger.info("Total build times: %s seconds", sum(buildTimes))
    logger.info("Max build time: %s seconds", max(buildTimes))
    logger.info("Min build time: %s seconds", min(buildTimes))
    logger.info("Average build time: %s seconds", average_build_times())
    logger.info("Standard error: %s", calculate_standard_error(buildTimes))


def save_results_to_json(filename):
    server_name = load("SERVER_NAME")
    num_builds = int(load("NUMBER_OF_BUILDS"))
    repeat = int(load("REPEAT"))

    result = {}

    result['successes'] = num_successes()
    result['failures'] = num_failures()
    result['average'] = average_build_times()
    result['standard_error'] = calculate_standard_error(buildTimes)
    result['server_name'] = server_name
    result['num_builds'] = num_builds
    result['repeat'] = repeat

    with open(filename, 'wb') as f:
        json.dump(result, f)


def printRecordIds():
    print('')
    for recordId, status in zip(recordIds, statuses):
        logger.info(SERVER_NAME + "/pnc-web/#/record/" + str(recordId) + "/info :: " + status)

    print('')

def sendBuildConfigsToServer(numberOfConfigs, repeat):
    buildConfigList = getBuildConfigList()

    for _ in range(repeat + 1):
        for i in range(numberOfConfigs):
            config = buildConfigList[i%len(buildConfigList)]
            config["name"] = randomName()
            config = json.dumps(config)
            r = post(SERVER_NAME + "/pnc-rest/rest/build-configurations/", config, headers=getHeaders())
            data = json.loads(r.content)
            buildId = getId(data)
            buildConfigIds.append(buildId)
            logger.info("Added build configuration %s", buildId)

def getBuildConfigList():
    configList = []
    with open(configListJson) as f:
        configList = json.loads(f.read())
    return configList

if __name__ == "__main__":
    SERVER_NAME = load("SERVER_NAME")
    USERNAME = load("USERNAME")
    PASSWORD = load("PASSWORD")
    REALM = load("REALM")
    CLIENT_ID = load("CLIENT_ID")
    KEYCLOAK_URL = load("KEYCLOAK_URL")
    NUMBER_OF_BUILDS = int(load("NUMBER_OF_BUILDS"))

    # if REPEAT_BUILDS = 0, do no repeat same build configurations
    # if REPEAT_BUILDS > 0, repeat the same build configurations REPEAT_BUILDS
    # times
    REPEAT_BUILDS = int(load("REPEAT"))

    sendBuildConfigsToServer(NUMBER_OF_BUILDS, REPEAT_BUILDS)
    fireBuilds(buildConfigIds)
    waitTillBuildsAreDone()
    getAllBuildTimes()
    getStatuses()
    printRecordIds()
    printStartStopTimes()
    printStats()
    save_results_to_json("driver_results.json")
