import pytest


@pytest.mark.parametrize("name,expected", [
    ("amazon-s3", "s3"),
    ("amazon-simple-storage-services-s3", "s3"),
    ("amazon-rds-for-oracle", "rds"),
    ("aws-iam-identity-center", "iam-identity-center"),
    ("amazon-fsx-netapp-ontap", "fsx-for-netapp-ontap"),
    ("amazon-kubernetes-service", "eks"),
])
def test_match_name(cat, name, expected):
    assert cat.match_name(name) == expected


@pytest.mark.parametrize("sdk,expected", [
    ("s3control", "s3"),
    ("bedrock-agent-runtime", "bedrock"),
    ("bedrock-agentcore-control", "bedrock-agentcore"),
    ("logs", "cloudwatch"),
    ("ec2-instance-connect", "ec2"),
    ("neptune-graph", "neptune"),
])
def test_match_botocore(cat, sdk, expected):
    assert cat.match_botocore(sdk) == expected


def test_match_text_prefers_specific_names(cat):
    assert cat.match_text("Bedrock AgentCore Gateway adds MCP servers") == ["mcp", "bedrock-agentcore"]
    assert "iam-identity-center" in cat.match_text("IAM Identity Center adds SCIM")
    assert "iam" not in cat.match_text("IAM Identity Center adds SCIM")


def test_match_text_ignores_ordinary_words(cat):
    assert cat.match_text("Using a lambda expression in Python") == []
    assert cat.match_text("my config backup failed") == []


def test_every_parent_exists(cat):
    for s in cat.services.values():
        assert s.parent is None or s.parent in cat.services, s.id
