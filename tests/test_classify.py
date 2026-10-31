from radar.classify import regions_for, services_for, tags_for

WHATS_NEW = {"id": "aws-whats-new", "type": "rss", "group": "aws-official"}
BLOGS = {"id": "aws-blogs", "type": "aws-blog-api", "group": "aws-official"}
BOTO = {"id": "botocore-changelog", "type": "github-changelog", "group": "aws-code"}
REDDIT = {"id": "reddit-aws", "type": "rss", "group": "community"}


def item(title, summary="", tags=()):
    return {"title": title, "summary": summary, "tags_raw": list(tags)}


def test_whats_new_product_tags_are_primary(cat):
    primary, mentioned = services_for(item("DAX in new Regions", tags=["general:products/amazon-dynamodb",
                                                                       "marketing:marchitecture/databases"]),
                                      WHATS_NEW, cat)
    assert primary == ["dynamodb"] and mentioned == []


def test_blog_with_many_tags_only_mentions_untitled_services(cat):
    it = item("How Toyota built an SAP platform with Amazon Bedrock",
              tags=["amazon-bedrock", "aws-lambda", "amazon-simple-storage-services-s3"])
    primary, mentioned = services_for(it, BLOGS, cat)
    assert primary == ["bedrock"]
    assert set(mentioned) == {"lambda", "s3"}


def test_govcloud_never_leads(cat):
    primary, _ = services_for(item("Kiro web search in GovCloud",
                                   tags=["general:products/aws-govcloud-us", "general:products/kiro"]),
                              WHATS_NEW, cat)
    assert primary[0] != "govcloud"


def test_botocore_names(cat):
    assert services_for(item("x", tags=["s3control"]), BOTO, cat)[0] == ["s3"]


def test_child_service_also_lists_parent(cat):
    primary, _ = services_for(item("EKS Anywhere adds Kubernetes 1.36"), REDDIT, cat)
    assert primary[:2] == ["eks-anywhere", "eks"]


def test_tags():
    assert "GA" in tags_for(item("X is now generally available"), WHATS_NEW)
    assert "preview" in tags_for(item("X now in preview"), WHATS_NEW)
    assert "region" in tags_for(item("DAX is now available in additional Regions"), WHATS_NEW)
    assert "deprecation" in tags_for(item("Lambda python3.10 is deprecated"), REDDIT)
    assert "instances" in tags_for(item("New m8g.24xlarge sizes"), WHATS_NEW)
    assert tags_for(item("Amazon EKS supports Gateway API"), WHATS_NEW) == ["feature"]
    assert "community" in tags_for(item("anything"), REDDIT)


def test_regions():
    it = item("DAX in more Regions", "Now in Africa (Cape Town), Canada (Central) and us-west-2.")
    assert regions_for(it, WHATS_NEW) == ["af-south-1", "ca-central-1", "us-west-2"]
    assert regions_for(it, REDDIT) == []
