# Deploy Cognite Function action
This action deploys a Python function to Cognite Functions, optionally with schedule(s).

## Inputs
### Function metadata in Github Workflow
#### Required
1. `function_external_id`: What we will use as `external_id` for the function. If it is not unique within your project, *the existing function will be overwritten*!
1. `function_folder`: Parent folder for the function's code. Everything within this folder will be uploaded (so if you need your special CSV-file; don't worry, it will automatically be included!)
1. `cdf_project`: The name of your CDF project.
1. `cdf_cluster`: The cluster your customer's CDF project lives in, like `westeurope-1` or `greenfield`.
1. `deployment_client_secret`: Client secret, only to be used for DEPLOYMENT of the function.
1. `deployment_client_id`:  Client ID, only to be used for DEPLOYMENT of the function.
1. `deployment_tenant_id`:  Tenant ID, only to be used for DEPLOYMENT of the function.

#### Required *if attaching schedules*
1. `schedule_file`: File location inside `function_folder` containing a list of schedules to be attached to your function. If this file exists, *then* `schedules_client_secret`, `schedules_client_id` and `schedules_tenant_id` will be required. Note: Schedule file will be ignored with a warning if it is pointing to a non-existing file. More details in section below.
1. `schedules_client_secret`: Client secret to be used at RUNTIME for the function, but ONLY for its scheduled runs! **Note: Calling the function normally, still uses the caller's credentials!**.
1. `schedules_client_id`:  Client ID to be used at RUNTIME for the function, but ONLY for its scheduled runs!
1. `schedules_tenant_id`:  Tenant ID to be used at RUNTIME for the function, but ONLY for its scheduled runs!

#### Optional
1. `remove_only`: **Short-cut**: Deletes function along with all attached schedules. Ignores most other parameters!
1. `common_folder`:  The path to the folder containing code that is shared between functions. See section below for more details.
1. `function_file`: The name of the file with your main function. Will default to `handler.py` if not given.
1. `function_secrets`: The *name* of a Github secret that holds the base64-encoded JSON dictionary with secrets (see "secrets section").
1. `data_set_id`: Data set ID to use for the file uploaded to CDF (the function-associated file: *zipped code folder*). Requires two *additional* DEPLOYMENT capabilities: 'dataset:READ' and 'files:WRITE' scoped to *either* the dataset you are going to use, or 'all'. Note: If your data set is WRITE PROTECTED, you also need to add the capability 'dataset:OWNER' for it. Read more about data sets in the official documentation: [Data sets](https://docs.cognite.com/cdf/data_governance/concepts/datasets/)
1. `description`: Additional field to describe the function.
1. `owner`: Additional field to describe the function owner.
1. `cpu`: Set fractional number of CPU cores per function. **Ignored for functions running on Azure!**. See defaults and allowed values in the [API documentation](https://docs.cognite.com/api/playground/#operation/post-api-playground-projects-project-functions).
1. `memory`: Set memory per function measured in GB. **Ignored for functions running on Azure!**. See defaults and allowed values in the [API documentation](https://docs.cognite.com/api/playground/#operation/post-api-playground-projects-project-functions).


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

### Example usage
[IN PROGRESS] Workflow to handle incoming Pull Requests:
See our repository [`deploy-templates-oidc`](https://github.com/cognitedata/deploy-functions-oidc) for the latest CI/CD workflow examples.

### Common folder
A common use case is that you do not want to replicate utility code between all function folders. In order to accommodate this, we copy all the contents in the folder specified by `common_folder` into the functions we upload to Cognite Functions. If this is not specified, we check if `common/` exists in the root folder and if so, _we use it_.

#### When using a common/shared folder, make sure you don't get a name conflict in one of your functions!

#### Handling imports
A typical setup looks like this:
```
├── common
│   └── utils.py
└── my_function
    └── handler.py
```
The code we zip and send off to the FilesAPI will look like this:
```
├── common
│   └── utils.py
└── handler.py
```
This means your `handler.py`-file should do imports from `common/utils.py` like this:
```py
from common.utils import my_helper1, my_helper2
import common.utils as utils  # alternative
```

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
...or use Python if you don't have `base64` available on your system:
```sh
$ echo '{"slack-token": "123-my-secret-api-key"}' | python -m base64
eyJzbGFjay10b2tlbiI6ICIxMjMtbXktc2VjcmV0LWFwaS1rZXkifQo=
```
To decode and verify it, do:
```sh
$ echo eyJzbGFjay10b2tlbiI6ICIxMjMtbXktc2VjcmV0LWFwaS1rZXkifQo= | base64 --decode
$ (Alternative using Python:)
$ echo eyJzbGFjay10b2tlbiI6ICIxMjMtbXktc2VjcmV0LWFwaS1rZXkifQo= | python -m base64 -d
{"slack-token": "123-my-secret-api-key"}
```
Take that encoded string and store it as a GitHub secret. This secret can now be used by referencing the name (case insensitive) of the secret in your workflow-file. Example:
```yaml
  function_secrets: ${{ secrets.my_secret_name }}
```

Notes: _Keys must be lowercase characters, numbers or dashes (-) and at most 15 characters. You can supply at most 5 secrets in the dictionary (Cognite Functions requirement)_
