#!/usr/bin/python

# Copyright: (c) 2024, David Villafaña <david.villafana@capcu.org>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
---
module: endpoint_central_patch_config.py

short_description: create a patch configuration

# If this is part of a collection, you need to use semantic versioning,
# i.e. the version is of the form "2.5.0" and not "2.4".
version_added: "1.0.0"

description: this creates a patch configuration via the Manage Engine API, so run_once should always be set to true

options:
    api_key:
        description: This is the auth key used to authenticate to Manage Engine
        required: true
        type: str
        no_log: true
    manage_engine_url:
        description: This is the URL of the Manage Engine instance
        required: true
        type: str
    manage_engine_port:
        description: This is the port of the Manage Engine instance
        required: true
        type: int
    name:
        description: This is the name of your patch configuration
        required: false
        type: str
        default: Ansible patch configuration
    desc:
        description: This is the description of your patch configuration
        required: false
        type: str
        default: Install select patches to devices
    deployment_policy_name:
        description: the policy name of the deployment policy
        required: true
        type: str
    hosts:
        description: the list of machine resource names, usually domain names
        required: true
        type: list
    patch_types:
        description: the types of patches you want applied to the hosts
        required: true
        type: list
    state:
        description: whether patch configuration should be present
        required: true
        type: str
        choices:
            - present


# Specify this value according to your collection
# in format of namespace.collection.doc_fragment_name
extends_documentation_fragment:
    - capcu.manage_engine.my_doc_fragment_name

author:
    - David Villafaña IV
"""

EXAMPLES = r"""
- name: ensure state present of patch install
  endpoint_central_patch_config.py:
    api_key: 7A69CA52-EASD-4162-A263-CC4DCC35736B
    manage_engine_url: ccudefend.capcu.org
    manage_engine_port: 8383
    name: Automated Windows Server updates - TEST
    deployment_policy_name: Update Servers
    hosts:
      - CCUTMSTEST
      - CCUWEBTEST
      - CCUAPPS2
    patch_types:
      - Cumulative Update for Windows Server
      - Servicing Stack Update for Windows Server
      - Cumulative Update for SQL Server
    state: present
  register: testout
  run_once: true
  delegate_to: localhost
"""

RETURN = r"""
api_response:
    description: The returned data from the api call that creates the patch configuration
    returned: always
    type: dict
    sample: {
                "changed": true,
                "failed": false,
                "message": {
                    "message_response": {
                        "installpatch": {}
                    },
                    "message_type": "installpatch",
                    "message_version": "1.3",
                    "status": "success"
                }
            }

"""

import json
import requests
from ansible.module_utils.basic import AnsibleModule
from typing import Callable


def get_resource_ids_for_patching(
    url: str, port: int, api_key: str, hosts: list[str]
) -> list[int]:
    """
    get_resource_ids_for_patching gets the list of resource ids of hosts to update

    Args:
        url: the url of the Manage Engine instance
        port: the port of the Manage Engine instance
        api_key: the auth token for the API
        endpoint: the endpoint to be posted with the data
        hosts: the list of host names
    Returns:
        a list of resource ids
    """
    all_systems = get_api_objects(url, port, api_key, "allsystems")
    selected_hosts = [x for x in all_systems if x["resource_name"] in hosts]
    ids: list[int] = [int(x["resource_id"]) for x in selected_hosts]
    return ids


def patch_hosts(
    fail_json: Callable,
    url: str,
    port: int,
    api_key: str,
    config_name: str,
    config_desc: str,
    policy_name: str,
    hosts: list[str],
    patch_types: list[str],
) -> dict:
    """
    Performs the patching of the hosts using abstracted logic

    Args:
        url: the url of the Manage Engine instance
        port: the port of the Manage Engine instance
        api_key: the auth token for the API
        patch_types: the types of patches to be applied
        hosts: the list of host names
    Returns:
        the API response as a dictionary
    """
    resource_ids: list[int] = get_resource_ids_for_patching(url, port, api_key, hosts)
    all_patches: list = get_api_objects(url, port, api_key, "allpatches")
    selected_patches: list = [
        x
        for x in all_patches
        if any(
            set(utype.split()).issubset(set(x["patch_description"].split()))
            for utype in patch_types
        )
        and int(x["missing"]) > 0
    ]
    patch_ids: list[int] = [x["patch_id"] for x in selected_patches]
    data: dict = {}
    try:
        policy_id = next(
            x
            for x in get_api_objects(url, port, api_key, "deploymentpolicies")
            if x["template_name"] == policy_name
        )["template_id"]
        data = {
            "PatchIDs": patch_ids,
            "ResourceIDs": resource_ids,
            "ConfigName": config_name,
            "ConfigDescription": config_desc,
            "actionToPerform": "Deploy",
            "DeploymentPolicyTemplateID": policy_id,
        }
    except StopIteration as e:
        fail_json(msg="failed to find deployment policy", changed=False, failed=True)

    endpoint: str = "patch/installpatch"
    resp: dict = api_post(url, port, api_key, endpoint=endpoint, data=json.dumps(data))
    return resp


def api_post(url: str, port: int, api_key: str, endpoint: str, data: dict) -> dict:
    """
    Posts to the specified endpoint of the ManageEngine v1.3 api
    Args:
        url: the url of the Manage Engine instance
        port: the port of the Manage Engine instance
        api_key: the auth token for the API
        endpoint: the endpoint to be posted with the data
        data: the payload for the API call
    Returns:
        the JSON api response as a dict
    """
    uri = f"{url}:{port}/api/1.3/{endpoint}"
    # Define the payload for the POST request
    headers = {"Authorization": api_key, "Content-Type": "application/json"}
    response = requests.post(uri, headers=headers, data=data)
    if response.status_code == 200:
        return json.loads(response.text)
    else:
        raise Exception(f"Error: {response.status_code}, {response.text}")


def get_api_objects(
    url: str, port: int, api_key: str, object_name: str, filter: str = ""
) -> list[dict]:
    """
    get_api_objects makes a simple unfiltered call to the ManageEngine API
    v1.4 for the object name specified and returns the first 1000 objects.
    Args:
        url: the url of the Manage Engine instance
        port: the port of the Manage Engine instance
        api_key: the auth token for the API
        object_name: the name of the object that is being fetched
    Returns:
        a list of the objects fetched
    """
    url = f"{url}:{port}/api/1.4/patch/{object_name}?=&page=1&pagelimit=1000{filter}"
    # Define the payload for the POST request
    headers = {"Authorization": api_key, "Content-Type": "application/json"}
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        objects = json.loads(response.text)["message_response"][object_name]
        return objects
    else:
        raise Exception(f"{response.status_code}")


def check_if_config_exists(
    fail_json: Callable,
    config_name: str,
    configs: list[dict],
    hosts: list[str],
) -> bool:
    try:
        exists: bool = any(
            (
                config["collection_name"].startswith(config_name)
                and not config["is_collection_deleted"]
                and config["total_target_count"] == len(hosts)
                and config["status_label"] != "dc.db.config.status.executed"
            )
            for config in configs
        )
        return exists
    except Exception as e:
        fail_json(
            msg=f"Failed to check existing configs {e}", changed=False, failed=True
        )


def run_module():
    # define available arguments/parameters a user can pass to the module
    module_args = dict(
        api_key=dict(type="str", required=True, no_log=True),
        manage_engine_url=dict(type="str", required=True),
        manage_engine_port=dict(type="int", required=True),
        name=dict(type="str", required=False, default="Ansible patch configuration"),
        desc=dict(type="str", required=False, default="Install select patches to devices"),
        deployment_policy_name=dict(type="str", required=True),
        hosts=dict(type="list", required=True),
        patch_types=dict(type="list", required=True),
        state=dict(type="str", choices=["present"], required=True),
    )

    # seed the result dict in the object
    # we primarily care about changed and state
    # changed is if this module effectively modified the target
    # state will include any data that you want your module to pass back
    # for consumption, for example, in a subsequent task
    result = dict(changed=False, msg="", failed=False)

    # the AnsibleModule object will be our abstraction working with Ansible
    # this includes instantiation, a couple of common attr would be the
    # args/params passed to the execution, as well as if the module
    # supports check mode
    module = AnsibleModule(argument_spec=module_args, supports_check_mode=False)

    api_key = module.params["api_key"]
    url = module.params["manage_engine_url"]
    url = url if "http" in url else f"https://{url}"
    port = module.params["manage_engine_port"]
    name = module.params["name"]
    desc = module.params["desc"]
    deployment_policy_name = module.params["deployment_policy_name"]
    hosts = module.params["hosts"]
    patch_types = module.params["patch_types"]
    state = module.params["state"]

    # if the user is working with this module in only check mode we do not
    # want to make any changes to the environment, just return the current
    # state with no modifications
    if module.check_mode:
        module.exit_json(**result)

    # manipulate or modify the state as needed (this is going to be the
    # part where your module will do what it needs to do)
    try:
        configs: list[dict] = get_api_objects(url, port, api_key, "viewconfig")
        config_exists: bool = check_if_config_exists(
            module.fail_json, name, configs, hosts
        )
        if state == "present":
            if config_exists:
                result["changed"] = False
                result["msg"] = "config already exists"
                result["failed"] = False
            else:
                resp: dict = patch_hosts(
                    fail_json=module.fail_json,
                    url=url,
                    port=port,
                    api_key=api_key,
                    config_name=name,
                    config_desc=desc,
                    policy_name=deployment_policy_name,
                    hosts=hosts,
                    patch_types=patch_types,
                )
                result["msg"] = resp
                if resp["status"] == "error":
                    result["changed"] = False
                    if resp["error_code"] == "3010":
                        result["failed"] = False
                    else:
                        result["failed"] = True
                        module.fail_json(**result)
                else:
                    result["changed"] = True
                    result["failed"] = False
    except Exception as e:
        module.fail_json(msg=f"failed to patch hosts: {e}", changed=False, failed=True)

    # in the event of a successful module execution, you will want to
    # simple AnsibleModule.exit_json(), passing the key/value results
    module.exit_json(**result)


def main():
    run_module()


if __name__ == "__main__":
    main()
