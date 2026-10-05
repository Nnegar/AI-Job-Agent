import yaml


with open("profile/career_profile.yaml", "r") as file:
    profile = yaml.safe_load(file)


print(profile["candidate"]["name"])

print(profile["career_identity"]["main_profile"])