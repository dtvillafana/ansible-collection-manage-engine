#!/usr/bin/python

# Copyright: (c) 2026, David Villafaña <david.villafana@capcu.org>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
from __future__ import absolute_import, division, print_function
from io import TextIOWrapper, BufferedReader

__metaclass__ = type

DOCUMENTATION = r"""
---
module: service_desk_plus_request

short_description: ensure state of a Service Desk Plus request ticket

# If this is part of a collection, you need to use semantic versioning,
# i.e. the version is of the form "2.5.0" and not "2.4".
version_added: "1.0.0"

description:
    - this creates a Service Desk Plus request ticket via the Manage Engine API, so run_once should always be set to true

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
    description:
        description: the description section of the request ticket
        required: false
        type: str
    attachments:
        description: list of attachments to add to the request
        required: false
        type: list
        elements: dict
        suboptions:
            file_name:
                description: display name of the attachment
                required: true
                type: str
            file_path:
                description: local filesystem path to the attachment
                required: true
                type: str
    requester_username:
        description: the username of the request creator
        required: true
        type: str
    status:
        description: the request status
        required: false
        type: str
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
    name: Service Desk Plus request ticket
    description: Update Servers - CCUTMSTEST CCUWEBTEST CCUAPPS2 - Cumulative Update for Windows Server - Servicing Stack Update for Windows Server - Cumulative Update for SQL Server
    attachments:
      - file_name: runbook.txt
        file_path: /tmp/runbook.txt
    requester_username: jdoe
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
from typing import Callable, Dict, List, Literal, Optional, Tuple, TypedDict, Union
from dataclasses import dataclass, asdict, field
import mimetypes

JSONValue = Union[
    None, bool, int, float, str, List["JSONValue"], Dict[str, "JSONValue"]
]


Attachment = Tuple[Literal["input_file"], Tuple[str, Optional[BufferedReader]], str]


@dataclass
class TMSRequester:
    id: int
    name: str


@dataclass
class TMSResolution:
    content: str


@dataclass
class TMSStatus:
    name: str


@dataclass
class TMSAttachment:
    file_name: str
    file_path: str
    file_type: Tuple[Optional[str], Optional[str]]
    # attachments: list[Attachment] = field(default_factory=lambda: [("input_file", ("", None), "")])

    def __init__(self, file_name: str, file_path: str):
        self.file_name = file_name
        self.file_path = file_path
        self.file_type = mimetypes.guess_file_type(self.file_path)

    def to_tuple(self):
        return (
            "input_file",
            (self.file_name, open(self.file_path, "rb"), self.file_type),
        )


@dataclass
class TMSRequest:
    id: Optional[int] = None
    subject: str = ""
    description: str = ""
    requester: Optional[TMSRequester] = None
    status: Optional[TMSStatus] = None
    resolution: Optional[TMSResolution] = None


def get_user_by_username(
    fail_json: Callable, api_key: str, url: str, port: int, username: str
) -> Optional[Dict[str, JSONValue]]:
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
            response_obj: JSONValue = json.loads(response.text)
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
    description: str,
    requester_username: str,
    status: str
) -> Dict[str, JSONValue]:
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
    headers = {"authtoken": api_key}

    requester_resp = get_user_by_username(
        fail_json=fail_json,
        api_key=api_key,
        url=url,
        port=port,
        username=requester_username,
    )
    if requester_resp:
        requester_id_val = requester_resp.get("id", None)
        if requester_id_val:
            requester_id = int(requester_id_val)
    requester = TMSRequester(id=requester_id, name=requester_username)
    data = TMSRequest(
        subject=request_name,
        description=description,
        resolution=TMSResolution(content="The update has completed successfully"),
        status=TMSStatus(name=status),
        requester=requester,
    )
    response = requests.post(
        url=f"{url}:{port}/api/v3/requests",
        headers=headers,
        data={"input_data": json.dumps({"request": asdict(data)})},
        verify=True,
    )
    if response.status_code in [200, 201]:
        ret = json.loads(response.text)["request"]
        return ret
    else:
        raise Exception(f"Error: {response.status_code}, {response.text}")


def get_api_objects(
    url: str, port: int, api_key: str, object_name: str
) -> List[Dict[str, JSONValue]]:
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
        objects: List[Dict[str, JSONValue]] = json.loads(response.text)[object_name]
        return objects
    else:
        raise Exception(
            f"Error getting API objects: {response.status_code}, {response.text}"
        )


def find_request(
    fail_json: Callable,
    request_name: str,
    requests: List[dict],
    description: List[str],
) -> Optional[Dict[str, JSONValue]]:
    try:
        request: Optional[Dict[str, JSONValue]] = next(
            (
                request
                for request in requests
                if (
                    request["subject"].startswith(request_name)
                    and request["status"]["name"] == "Open"
                    and description in request["short_description"]
                )
            ),
            None,
        )
        return request
    except Exception as e:
        fail_json(
            msg=f"Failed to find existing request {e}", changed=False, failed=True
        )


def add_and_associate_attachments(
    request_id: str,
    attachments: List[Dict[str, str]],
    fail_json: Callable,
    base_url: str,
    port: int,
    api_key: str,
) -> JSONValue:

    tms_attachments: List[Attachment] = [
        TMSAttachment(file_path=x["file_path"], file_name=x["file_name"]).to_tuple()
        for x in attachments
    ]

    headers = {"authtoken": api_key}
    url: str = f"{base_url}:{port}/api/v3/requests/{request_id}/upload"
    response = requests.put(
        url=url,
        headers=headers,
        files=tms_attachments,
        verify=True,
    )
    if response.status_code in [200, 201]:
        ret = json.loads(response.text).get("attachment", None)
        return ret
    else:
        raise Exception(f"Error: {response.status_code}, {response.text}, {url}")


def check_api_resp(
    module: AnsibleModule, result: Dict[str, JSONValue], response
) -> Dict[str, JSONValue]:
    result["msg"].append(response)
    if response.get("status", "") == "error":
        result["changed"] = False
        if response["error_code"] == "3010":
            result["failed"] = False
        else:
            result["failed"] = True
            module.fail_json(**result)
    else:
        result["changed"] = True
        result["failed"] = False
    return result


def run_module():
    # define available arguments/parameters a user can pass to the module
    module_args = dict(
        api_key=dict(type="str", required=True, no_log=True),
        service_desk_plus_url=dict(type="str", required=True),
        service_desk_plus_port=dict(type="int", required=True),
        name=dict(type="str", required=False, default="Request created by Ansible"),
        description=dict(type="str", required=False, default="Default Description"),
        state=dict(type="str", choices=["present", "absent"], required=True),
        attachments=dict(
            type="list",
            required=False,
            elements="dict",
            options=dict(
                file_name=dict(type="str", required=True),
                file_path=dict(type="str", required=True),
            ),
        ),
        requester_username=dict(type="str", required=True),
        status=dict(type="str", required=False, default="Open"),
    )

    # seed the result dict in the object
    # we primarily care about changed and state
    # changed is if this module effectively modified the target
    # state will include any data that you want your module to pass back
    # for consumption, for example, in a subsequent task
    result = dict(changed=False, msg=[], failed=False)

    # the AnsibleModule object will be our abstraction working with Ansible
    # this includes instantiation, a couple of common attr would be the
    # args/params passed to the execution, as well as if the module
    # supports check mode
    module = AnsibleModule(argument_spec=module_args, supports_check_mode=False)

    api_key: str = module.params["api_key"]
    base_url: str = module.params["service_desk_plus_url"]
    base_url = base_url if "http" in base_url else f"https://{base_url}"
    port: int = module.params["service_desk_plus_port"]
    name: str = module.params["name"]
    description: str = module.params["description"]
    state: str = module.params["state"]
    status: str = module.params["status"]
    attachments: List[Dict[str, str]] = module.params["attachments"]
    requester_username: str = module.params["requester_username"]

    # if the user is working with this module in only check mode we do not
    # want to make any changes to the environment, just return the current
    # state with no modifications
    if module.check_mode:
        module.exit_json(**result)

    # manipulate or modify the state as needed (this is going to be the
    # part where your module will do what it needs to do)
    try:
        requests: List[Dict[str, JSONValue]] = get_api_objects(
            base_url, port, api_key, "requests"
        )
        request: Optional[Dict[str, JSONValue]] = find_request(
            fail_json=module.fail_json,
            request_name=name,
            requests=requests,
            description=description
        )
        if state == "present":
            if request:
                result["changed"] = False
                result["msg"].append("request already exists")
                result["failed"] = False
            else:
                request_resp: Dict[str, JSONValue] = create_tms_request(
                    fail_json=module.fail_json,
                    url=base_url,
                    port=port,
                    api_key=api_key,
                    request_name=name,
                    description=description,
                    requester_username=requester_username,
                    status=status
                )
                result = check_api_resp(module, result, request_resp)
                if (
                    attachments
                    and request_resp.get("id", None)
                    and isinstance(request_resp["id"], str)
                ):
                    attachments_resp: JSONValue = add_and_associate_attachments(
                        request_id=request_resp["id"],
                        fail_json=module.fail_json,
                        base_url=base_url,
                        port=port,
                        api_key=api_key,
                        attachments=attachments,
                    )
                    result = check_api_resp(module, result, attachments_resp)
        elif state == "absent":
            if not request:
                result["changed"] = False
                result["msg"].append("request does not exist")
                result["failed"] = False
            else:
                delete_resp: dict = delete_tms_ticket(
                    fail_json=module.fail_json,
                    url=base_url,
                    port=port,
                    api_key=api_key,
                    request_id=request["id"],
                )
                result["msg"].append(delete_resp)
                if delete_resp["response_status"]["status"] == "success":
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
