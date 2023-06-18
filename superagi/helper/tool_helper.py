import importlib.util
import inspect
import json
import os
import sys
import zipfile
from urllib.parse import urlparse

import requests

from superagi.config.config import get_config
from superagi.models.tool import Tool
from superagi.models.tool_config import ToolConfig
from superagi.models.tool_kit import ToolKit
from superagi.tools.base_tool import BaseTool
from superagi.tools.base_tool import BaseToolKit


def parse_github_url(github_url):
    parts = github_url.split('/')
    owner = parts[3]
    repo = parts[4]
    branch = "main"
    return f"{owner}/{repo}/{branch}"


def download_tool(tool_url, target_folder):
    parsed_url = parse_github_url(tool_url)
    parts = parsed_url.split("/")
    path = "/"
    owner, repo, branch = parts[0], parts[1], parts[2]
    archive_url = f"https://api.github.com/repos/{owner}/{repo}/zipball/{branch}"
    response = requests.get(archive_url)
    tool_zip_file_path = os.path.join(target_folder, 'tool.zip')

    with open(tool_zip_file_path, 'wb') as f:
        f.write(response.content)

    print("Reading Zip")
    with zipfile.ZipFile(tool_zip_file_path, 'r') as z:
        members = [m for m in z.namelist() if m.startswith(f"{owner}-{repo}") and f"{path}" in m]

        # Extract only folders in the root directory
        root_folders = [member for member in members if member.count('/') > 1]
        for member in root_folders:
            archive_folder = f"{owner}-{repo}"
            target_name = member.replace(f"{archive_folder}/", "", 1)

            # Skip the unique hash folder while extracting:
            segments = target_name.split('/', 1)
            if len(segments) > 1:
                target_name = segments[1]
            else:
                continue

            target_path = os.path.join(target_folder, target_name)

            if not target_name:
                continue

            if member.endswith('/'):
                os.makedirs(target_path, exist_ok=True)
            else:
                with open(target_path, 'wb') as outfile, z.open(member) as infile:
                    outfile.write(infile.read())
    print("Donwload Success!")
    os.remove(tool_zip_file_path)


def get_classes_in_file(file_path, clazz):
    classes = []

    # Load the module from the file
    module = load_module_from_file(file_path)

    # Iterate over all members of the module
    for name, member in inspect.getmembers(module):
        # Check if the member is a class and extends BaseTool
        if inspect.isclass(member) and issubclass(member, clazz) and member != clazz:
            class_dict = {}
            class_dict['class_name'] = member.__name__

            class_obj = getattr(module, member.__name__)
            try:
                obj = class_obj()
                if clazz == BaseToolKit:
                    class_dict['tool_kit_name'] = obj.name
                    class_dict['tool_kit_description'] = obj.description
                    class_dict['tool_kit_tools'] = obj.get_tools()
                    class_dict['tool_kit_keys'] = obj.get_env_keys()
                    classes.append(class_dict)
                elif clazz == BaseTool:
                    # print("FOUND BASE TOOL__________")
                    class_dict['tool_name'] = obj.name
                    class_dict['tool_description'] = obj.description
                    classes.append(class_dict)
                    # print(obj.name)
            except:
                class_dict = None
    return classes


def load_module_from_file(file_path):
    spec = importlib.util.spec_from_file_location("module_name", file_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    return module


def init_tools(folder_path, session, tool_name_to_tool_kit):
    print("__________________________________INIT TOOLS______________________________________")

    # Iterate over all subfolders
    for folder_name in os.listdir(folder_path):
        folder_dir = os.path.join(folder_path, folder_name)
        # Iterate over all files in the subfolder
        if os.path.isdir(folder_dir):
            # sys.path.append(os.path.abspath('superagi/tools/email'))
            sys.path.append(folder_dir)
            for file_name in os.listdir(folder_dir):
                file_path = os.path.join(folder_dir, file_name)
                if file_name.endswith(".py") and not file_name.startswith("__init__"):
                    # Get classes
                    classes = get_classes_in_file(file_path=file_path, clazz=BaseTool)
                    for clazz in classes:
                        if clazz["class_name"] is not None:
                            tool_name = clazz['tool_name']
                            tool_description = clazz['tool_description']
                            tool_kit_id = tool_name_to_tool_kit.get(tool_name, None)
                            if tool_kit_id is not None:
                                new_tool = Tool.add_or_update(session, tool_name=tool_name, folder_name=folder_name,
                                                              class_name=clazz['class_name'], file_name=file_name,
                                                              tool_kit_id=tool_name_to_tool_kit[tool_name],
                                                              description=tool_description)
                                print("Updated Tool path details for tool : ", new_tool)
                            else:
                                print("Tool Kit Not Found for tool : ", tool_name)


def init_tool_kits(code_link, existing_toolkits, folder_path, organisation, session):
    print("__________________________________INIT TOOL KITS______________________________________")
    tool_name_to_tool_kit = {}
    new_toolkits = []
    # Iterate over all subfolders
    for folder_name in os.listdir(folder_path):
        folder_dir = os.path.join(folder_path, folder_name)

        if os.path.isdir(folder_dir):
            # sys.path.append(os.path.abspath('superagi/tools/email'))
            sys.path.append(folder_dir)
            # Iterate over all files in the subfolder
            for file_name in os.listdir(folder_dir):
                file_path = os.path.join(folder_dir, file_name)
                if file_name.endswith(".py") and not file_name.startswith("__init__"):
                    # Get classes
                    print("FILE : ",file_path)
                    classes = get_classes_in_file(file_path=file_path, clazz=BaseToolKit)
                    for clazz in classes:
                        # print("FInal", clazz["tool_kit_description"])
                        if clazz["class_name"] is not None:
                            toolkit_name = clazz["tool_kit_name"]
                            toolkit_description = clazz["tool_kit_description"]
                            tools = clazz["tool_kit_tools"]
                            tool_config_keys = clazz["tool_kit_keys"]
                            # Create a new ToolKit object
                            new_toolkit = ToolKit.add_or_update(
                                session,
                                name=toolkit_name,
                                description=toolkit_description,
                                show_tool_kit=True if len(tools) > 1 else False,
                                organisation_id=organisation.id,
                                tool_code_link=code_link
                            )
                            new_toolkits.append(new_toolkit)
                            tool_mapping = {}
                            # Store the tools in the database
                            for tool in tools:
                                # print("INSIDE TOOLS")
                                new_tool = Tool.add_or_update(session, tool_name=tool.name, folder_name=None,
                                                              class_name=None, file_name=None,
                                                              tool_kit_id=new_toolkit.id, description=tool.description)
                                tool_mapping[tool.name] = new_toolkit.id
                            tool_name_to_tool_kit = {**tool_mapping, **tool_name_to_tool_kit}

                            # Store the tools config in the database
                            for tool_config_key in tool_config_keys:
                                new_config = ToolConfig.add_or_update(session, tool_kit_id=new_toolkit.id,
                                                                      key=tool_config_key)
    # Delete toolkits that are not present in the updated toolkits
    # print("EXISTING TOOLS : ___________")
    # print(existing_toolkits)
    # print("NEW FINAL TOOLS : ___________")
    # print(new_toolkits)
    for toolkit in existing_toolkits:
        if toolkit.name not in [new_toolkit.name for new_toolkit in new_toolkits]:
            session.query(Tool).filter(Tool.tool_kit_id == toolkit.id).delete()
            session.query(ToolConfig).filter(ToolConfig.tool_kit_id == toolkit.id).delete()
            # print("_______________DELETEING________________")
            # print(toolkit)
            session.delete(toolkit)
    # Commit the changes to the database
    session.commit()
    return tool_name_to_tool_kit


def process_files(folder_path, session, organisation, code_link=None):
    print("GETTING TOOLKITS OF : ")
    print(organisation)
    existing_toolkits = session.query(ToolKit).filter(ToolKit.organisation_id == organisation.id).all()

    # tool_name_to_tool_kit = []
    tool_name_to_tool_kit = init_tool_kits(code_link, existing_toolkits, folder_path, organisation, session)
    init_tools(folder_path, session, tool_name_to_tool_kit)


def get_readme_content_from_code_link(tool_code_link):
    parsed_url = urlparse(tool_code_link)
    path_parts = parsed_url.path.split("/")
    print(path_parts)

    # Extract username, repository, and branch from the URL
    username = path_parts[1]
    repository = path_parts[2]
    branch = path_parts[4] if len(path_parts) > 4 else "main"

    readme_url = f"https://raw.githubusercontent.com/{username}/{repository}/{branch}/README.MD"
    print("README ", readme_url)
    response = requests.get(readme_url)
    if response.status_code == 404:
        readme_url = f"https://raw.githubusercontent.com/{username}/{repository}/{branch}/README.md"
        response = requests.get(readme_url)
    readme_content = response.text
    return readme_content


def register_tool_kits(session, organisation):
    folder_path = get_config("TOOLS_DIR")
    if folder_path is None:
        folder_path = "superagi/tools"
    if organisation is not None:
        process_files(folder_path, session, organisation)
        # print("__________________________INPUT TOOL PARSING__________________")
        # process_files("superagi/.input_tools", session, organisation)


def extract_repo_name(repo_link):
    # Extract the repository name from the link
    # Assuming the GitHub link format: https://github.com/username/repoName
    repo_name = repo_link.rsplit('/', 1)[-1]

    return repo_name


def add_tool_to_json(repo_link):
    # Read the content of the tools.json file
    with open('tools.json', 'r') as file:
        tools_data = json.load(file)

    # Extract the repository name from the link
    repo_name = extract_repo_name(repo_link)

    # Add a new key-value pair to the tools object
    tools_data['tools'][repo_name] = repo_link

    # Write the updated JSON object back to tools.json
    with open('tools.json', 'w') as file:
        json.dump(tools_data, file, indent=2)

# # Example usage
# repo_link = "https://github.com/Autocop-Agent/discord"
# add_tool_to_json(repo_link)