#!/usr/bin/python

# Copyright: (c) 2024, David Villafaña <david.villafana@capcu.org>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
---
module: service_desk_plus_request

short_description: ensure state of a Sevice Desk Plus request ticket

# If this is part of a collection, you need to use semantic versioning,
# i.e. the version is of the form "2.5.0" and not "2.4".
version_added: "1.0.0"

description:
    - this creates a Sevice Desk Plus request ticket via the Manage Engine API, so run_once should always be set to true

author:
    - David Villafaña IV

requirements: []

options:
    api_key:
        description: This is the auth key used to authenticate to Manage Engine
        required: true
        type: str
        no_log: true
    service_desk_plus_url:
        description: This is the URL of the Manage Engine instance
        required: true
        type: str
    service_desk_plus_port:
        description: This is the port of the Manage Engine instance
        required: true
        type: int
    name:
        description: This is the name of your Sevice Desk Plus request ticket
        required: false
        type: str
        default: Request created by Ansible
    deployment_policy_name:
        description: the policy name of the deployment policy
        required: false
        type: str
    hosts:
        description: the list of machine resource names, usually domain names
        required: true
        type: list
    patch_types:
        description: the types of patches you want applied to the hosts
        required: false
        type: list
    state:
        description: whether patch configuration should be present
        required: true
        type: str
        choices:
            - present
            - absent
"""

EXAMPLES = r"""
- name: ensure state present of patch install
  service_desk_plus_request:
    api_key: 7A69CA52-EASD-4162-A263-CC4DCC35736B
    service_desk_plus_url: tms.capcu.org
    service_desk_plus_port: 8080
    name: Sevice Desk Plus request ticket
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
from typing import Callable, Optional


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


def get_user_by_username(
    fail_json: Callable, api_key: str, url: str, port: int, username: str
) -> dict:
    """
    retrieve user from TMS API by AD username

    Args:
        url: the url of the Manage Engine instance
        port: the port of the Manage Engine instance
        api_key: the auth token for the API
        username: the username

    Returns:
        the user object from the API
    """
    try:
        endpoint = "users"
        headers = {"authtoken": api_key}
        params = {
            "list_info": {
                "start_index": 1,
                "sort_field": "name",
                "sort_order": "asc",
                "row_count": 100,
                "get_total_count": True,
                "search_fields": {"name": username},
            },
            "fields_required": [
                "name",
                "is_technician",
                "citype",
                "login_name",
                "email_id",
                "department",
                "phone",
                "mobile",
                "jobtitle",
                "project_roles",
                "employee_id",
                "first_name",
                "middle_name",
                "last_name",
                "is_vipuser",
                "ciid",
            ],
        }
        response = requests.get(
            url=f"{url}:{port}/api/v3/{endpoint}",
            headers=headers,
            params={"input_data": json.dumps(params)},
            verify=True,
        )
        if response.status_code in [200, 201]:
            response_obj = json.loads(response.text)
            users = response_obj["users"]
            user = users[0]
            return user
        else:
            raise Exception(f"{response.status_code}, {response.text}")
        # should only return 1 user since login_name is unique
    except Exception as e:
        fail_json(msg=f"Error getting user by username: {e}")


def delete_tms_ticket(
    fail_json: Callable, url: str, port: int, api_key: str, request_id: int
) -> dict:
    """
    Delete TMS ticket by API

    Args:
        fail_json: the fail_json to call upon error
        url: the url of the Manage Engine instance
        port: the port of the Manage Engine instance
        api_key: the auth token for the API
        request_id: the id of the object that is being deleted

    Returns:
        the request object returned by the API
    """
    url = f"{url}:{port}/api/v3/requests/{request_id}/move_to_trash"
    headers = {"authtoken": api_key}
    response = requests.delete(url, headers=headers, verify=True)
    if response.status_code in [200, 201]:
        return json.loads(response.text)
    else:
        raise Exception(f"Error: {response.status_code}, {response.text}")


def create_tms_request(
    fail_json: Callable,
    url: str,
    port: int,
    api_key: str,
    request_name: str,
    policy_name: str,
    hosts: str,
    patch_types: str,
) -> dict:
    """
    Create TMS ticket by TMS API for an automation job

    Args:
        fail_json: the fail_json to call upon error
        url: the url of the Manage Engine instance
        port: the port of the Manage Engine instance
        api_key: the auth token for the API
        request_name: the name of the request that is being created

    Returns:
        the request object returned by the API
    """
    endpoint = "requests"
    headers = {"authtoken": api_key}
    data = {
        "request": {
            "subject": request_name,
            "description": f"[AUTO-GENERATED] Ansible has initiated {patch_types} updates for the following servers : {hosts} {f'in accordance with the {{ {policy_name} }} policy' if policy_name else ''}",
            "requester": {
                "id": int(
                    get_user_by_username(
                        fail_json=fail_json,
                        api_key=api_key,
                        url=url,
                        port=port,
                        username="sv-automation",
                    )["id"]
                ),
                "name": "automation",
            },
            "resolution": {"content": "The update has completed successfully"},
            "status": {"name": "Open"},
        }
    }
    response = requests.post(
        url=f"{url}:{port}/api/v3/{endpoint}",
        headers=headers,
        data={"input_data": json.dumps(data)},
        verify=True,
    )
    if response.status_code in [200, 201]:
        ret = json.loads(response.text)["request"]
        return ret
    else:
        raise Exception(f"Error: {response.status_code}, {response.text}")


def get_api_objects(url: str, port: int, api_key: str, object_name: str) -> list[dict]:
    """
    get_api_objects makes a simple unfiltered call to the ManageEngine API
    v3 for the object name specified and returns the first 1000 objects.
    Args:
        url: the url of the Manage Engine instance
        port: the port of the Manage Engine instance
        api_key: the auth token for the API
        object_name: the name of the object that is being fetched
    Returns:
        a list of the objects fetched
    """
    url = f"{url}:{port}/api/v3/{object_name}"
    # Define the payload for the GET request
    headers = {"authtoken": api_key, "Content-Type": "application/json"}
    params = {
        "input_data": json.dumps(
            {"list_info": {"row_count": 1000, "sort_order": "desc"}}
        )
    }
    response = requests.get(url, headers=headers, params=params)
    if response.status_code in [200, 201]:
        objects = json.loads(response.text)[object_name]
        return objects
    else:
        raise Exception(
            f"Error getting API objects: {response.status_code}, {response.text}"
        )


def find_request(
    fail_json: Callable,
    request_name: str,
    requests: list[dict],
    hosts: list[str],
    patch_types: list[str],
) -> Optional[dict]:
    try:
        request: bool = next(
            (
                request
                for request in requests
                if (
                    request["subject"].startswith(request_name)
                    and request["status"]["name"] == "Open"
                    and all(s in request["short_description"] for s in hosts)
                    and all(s in request["short_description"] for s in patch_types)
                )
            ),
            None,
        )
        return request
    except Exception as e:
        fail_json(
            msg=f"Failed to find existing request {e}", changed=False, failed=True
        )


def run_module():
    # define available arguments/parameters a user can pass to the module
    module_args = dict(
        api_key=dict(type="str", required=True, no_log=True),
        service_desk_plus_url=dict(type="str", required=True),
        service_desk_plus_port=dict(type="int", required=True),
        name=dict(type="str", required=False, default="Request created by Ansible"),
        deployment_policy_name=dict(type="str", required=False),
        hosts=dict(type="list", required=True),
        patch_types=dict(type="list", required=False),
        state=dict(type="str", choices=["present", "absent"], required=True),
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

    api_key: str = module.params["api_key"]
    url: str = module.params["service_desk_plus_url"]
    url = url if "http" in url else f"https://{url}"
    port: int = module.params["service_desk_plus_port"]
    name: str = module.params["name"]
    deployment_policy_name: str = module.params["deployment_policy_name"]
    hosts: list[str] = module.params["hosts"]
    patch_types: list[str] = module.params["patch_types"]
    state: str = module.params["state"]

    # if the user is working with this module in only check mode we do not
    # want to make any changes to the environment, just return the current
    # state with no modifications
    if module.check_mode:
        module.exit_json(**result)

    # manipulate or modify the state as needed (this is going to be the
    # part where your module will do what it needs to do)
    try:
        requests: list[dict] = get_api_objects(url, port, api_key, "requests")
        request: Optional[dict] = find_request(
            fail_json=module.fail_json,
            request_name=name,
            requests=requests,
            hosts=hosts,
            patch_types=patch_types,
        )
        if state == "present":
            if request:
                result["changed"] = False
                result["msg"] = "request already exists"
                result["failed"] = False
            else:
                resp: dict = create_tms_request(
                    fail_json=module.fail_json,
                    url=url,
                    port=port,
                    api_key=api_key,
                    request_name=name,
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
        elif state == "absent":
            if not request:
                result["changed"] = False
                result["msg"] = "request does not exist"
                result["failed"] = False
            else:
                resp: dict = delete_tms_ticket(
                    fail_json=module.fail_json,
                    url=url,
                    port=port,
                    api_key=api_key,
                    request_id=request["id"],
                )
                result["msg"] = resp
                if resp["response_status"]["status"] == "success":
                    result["changed"] = True
                    result["failed"] = False
                else:
                    result["failed"] = True
                    result["changed"] = False
                    module.fail_json(**result)
    except Exception as e:
        module.fail_json(
            msg=f"failed to create request: {e}", changed=False, failed=True
        )
    # in the event of a successful module execution, you will want to
    # simple AnsibleModule.exit_json(), passing the key/value results
    module.exit_json(**result)


def main():
    run_module()


if __name__ == "__main__":
    main()
