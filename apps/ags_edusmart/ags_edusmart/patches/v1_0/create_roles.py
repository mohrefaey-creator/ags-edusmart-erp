# Runs in pre_model_sync: DocType permission rows Link to Role, so a role added
# in a later release must exist before its DocType JSON is imported.
from ags_edusmart.setup.roles import create_roles


def execute():
	create_roles()
