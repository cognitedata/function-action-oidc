# Deploy Cognite Function action
This action deploys a Python function to Cognite Functions, optionally with schedule(s).

## Inputs 

### Required
| Parameter | Description
|:-|:-
| `function_external_id` | What we will use as `external_id` for the function. If it is not unique within your project, *the existing function will be overwritten*!
| `function_folder` | Parent folder for the function's code. Everything within this folder will be uploaded (so if you need your special CSV-file; don't worry, it will automatically be included!)
| `cdf_project` | The name of your CDF project.
| `cdf_cluster` | The cluster your customer's CDF project lives in, like `westeurope-1` or `greenfield`.
| `deployment_client_secret` | Client secret, only to be used for DEPLOYMENT of the function.
| `deployment_client_id` |  Client ID, only to be used for DEPLOYMENT of the function.
| `deployment_tenant_id` |  Tenant ID, only to be used for DEPLOYMENT of the function.

### Required *if attaching schedules*
| Parameter | Description
|:-|:-
| `schedule_file` | File location inside `function_folder` containing a list of schedules to be attached to your function. If this file exists, *then* `schedules_client_secret`, `schedules_client_id` and `schedules_tenant_id` will be required. Note: Schedule file will be ignored with a warning if it is pointing to a non-existing file. More details in section below.
| `schedules_client_secret` | Client secret to be used at RUNTIME for the function, but ONLY for its scheduled runs! **Note: Calling the function normally, still uses the caller's credentials!**.
| `schedules_client_id` |  Client ID to be used at RUNTIME for the function, but ONLY for its scheduled runs!
| `schedules_tenant_id` |  Tenant ID to be used at RUNTIME for the function, but ONLY for its scheduled runs!

<ul>

### Schedule file format [`.yaml`]
```yaml
- name: Daily schedule
  cron: "0 0 * * *"
  data:
    lovely-parameter: True
    something-else: 42
- name: Hourly schedule
  cron: "0 * * * *"
  data:
    lovely-parameter: False
    something-else: 777
- name: Hourly schedule  # Same name as another schedule (allowed), but with no `data` (also allowed).
  cron: "0 * * * *"
```
</ul>

### Optional
All optional parameters that has default values, can be found in `src/defaults.py`, i.e. they are *not* defined in `action.yaml` because of the typical multi-deploy-pattern used with this action.
| Parameter | Description
|:-|:-
| `remove_only` | Deletes function along with all attached schedules. Ignores most other parameters!
| `common_folder` |  The path to the folder containing code that is shared between functions. *Note: See [Common folder](#common-folder) for more details*
| `function_file` | The name of the file with your main function. Will default to `handler.py` if not given.
| `function_secrets` | The *name* of a Github secret that holds the base64-encoded JSON dictionary with secrets (see "secrets section").
| `function_deploy_timeout` | The timeout limit (in seconds) for the function deployment. Once the timeout is reached, the deployment is canceled (an attempt to delete the function will be made).
| `data_set_id` | Data set ID to use for the file uploaded to CDF (the function-associated file: *zipped code folder*). Requires two *additional* DEPLOYMENT capabilities: 'dataset:READ' and 'files:WRITE' scoped to *either* the dataset you are going to use, or 'all'. Note: If your data set is WRITE PROTECTED, you also need to add the capability 'dataset:OWNER' for it. Read more about data sets in the official documentation: [Data sets](https://docs.cognite.com/cdf/data_governance/concepts/datasets/)
| `post_deploy_cleanup` | Delete the code file object from CDF Files after successful Function deployment. Defaults to true.
| `description` | Additional field to describe the function.
| `owner` | Additional field to describe the function owner.
| `env_vars` | Environment variables for your function. Accepts JSON with string key/value pairs, like `{"FOO_BAR": "baz", "another_env_var": "cool"}`.
| `cpu` | Set fractional number of CPU cores per function. You may check the default and the allowed values (they vary with the CDF project's cloud provider) by calling the `/limits` endpoint of the [Functions API (documentation)](https://docs.cognite.com/api/playground/#operation/get-functions-limits).
| `memory` | Set memory per function measured in GB. You may check the default and the allowed values (they vary with the CDF project's cloud provider) by calling the `/limits` endpoint of the [Functions API (documentation)](https://docs.cognite.com/api/playground/#operation/get-functions-limits).
| `runtime` | The function runtime. Check the default and allowed values/versions in the [API documentation](https://docs.cognite.com/api/playground/#operation/post-api-playground-projects-project-functions).
| `metadata` | Set custom metadata for the function. Accepts JSON with string key/value pairs. For example, `'{"version":"1.0.0","released":"2022-09-14"}'`. Check the [API documentation](https://cognite-sdk-python.readthedocs-hosted.com/en/latest/cognite.html#cognite.client._api.functions.FunctionsAPI.create) for allowed values and limitations.
| `index_url` | Index URL for Python Package Manager to use. Be aware of the intrinsic security implications of using the index_url option. Check the [API documentation](https://cognite-sdk-python.readthedocs-hosted.com/en/latest/cognite.html#cognite.client._api.functions.FunctionsAPI.create) for allowed values and limitations.
| `extra_index_urls` | Extra Index URLs for Python Package Manager to use. Accepts JSON encoded list of strings, for example: `'["http://foo.bar", "https://bar.baz"]'`. Be aware of the intrinsic security implications of using the extra_index_urls option. Check the [API documentation](https://cognite-sdk-python.readthedocs-hosted.com/en/latest/cognite.html#cognite.client._api.functions.FunctionsAPI.create) for allowed values and limitations.


## Common folder
A common use case is that you do not want to replicate utility code between all function folders. In order to accommodate this, we copy all the contents in the folder specified by `common_folder` into the functions we upload to Cognite Functions. If `common_folder` *is not provided*, only the function folder is packed into the zip file.

**_NOTE:_** When using a common/shared folder, make sure you don't get a name conflict in one of your functions!
<ul>

### Handling common imports
A typical setup looks like this:
```
└── functions
    ├──common
    │  └── utils.py
    └──my_function
       └── handler.py
```

and your import would look like this:
```py
import sys
sys.path.append(f"{sys.path[0]}/..")
from common.utils import my_helper1, my_helper2
```

The code we zip and send off to the FilesAPI will look like this:
```
├── common
│   └── utils.py
└── handler.py
```

This means your `handler.py` should import from `common/utils.py` like this:
```py
try: # Cognite Function
    from common.utils import my_helper1, my_helper2
except ModuleNotFoundError: # Local development
    import sys
    sys.path.append(f"{sys.path[0]}/..")
    from common.utils import my_helper1, my_helper2
```
</ul>

### Function secrets
When you implement your Cognite Function, you may need to have additional `secrets`, for example if you want to to talk to a 3rd party service like Slack.
To achieve this, you could create the following dictionary:
```json
{"slack-token": "123-my-secret-api-key"}
```
Use your terminal to encode your credentials into a string:
```shell script
$ echo '{"slack-token": "123-my-secret-api-key"}' | base64
eyJzbGFjay10b2tlbiI6ICIxMjMtbXktc2VjcmV0LWFwaS1rZXkifQo=
```
To decode and verify it, do:
```sh
$ echo eyJzbGFjay10b2tlbiI6ICIxMjMtbXktc2VjcmV0LWFwaS1rZXkifQo= | base64 --decode
```
...or use Python if you don't have `base64` available on your system:
```sh
$ echo '{"slack-token": "123-my-secret-api-key"}' | python -m base64
eyJzbGFjay10b2tlbiI6ICIxMjMtbXktc2VjcmV0LWFwaS1rZXkifQo=
```
To decode and verify it, do:
```sh
$ echo eyJzbGFjay10b2tlbiI6ICIxMjMtbXktc2VjcmV0LWFwaS1rZXkifQo= | python -m base64 -d
{"slack-token": "123-my-secret-api-key"}
```
Take that encoded string and store it as a GitHub secret. This secret can now be used by referencing the name (case insensitive) of the secret in your workflow-file. Example:
```yaml
  function_secrets: ${{ secrets.my_secret_name }}
```

Notes: _Keys must be lowercase characters, numbers or dashes (-) and at most 15 characters. You can supply at most 5 secrets in the dictionary (Cognite Functions requirement)_
