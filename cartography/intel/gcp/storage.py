import logging

from googleapiclient.discovery import HttpError

from cartography.intel.gcp import compute
from cartography.util import run_cleanup_job
logger = logging.getLogger(__name__)

def get_gcp_bucket_iam_policy(storage, bucket):
    """
    Retrieves IAM policy about the given bucket.
    
    :type storage: A storage resource object
    :param storage: The storage resource object created by googleapiclient.discovery.build()
    
    :type bucket: str
    :param bucket: Google Cloud Bucket name
    
    :rtype: IAM Policy Object 
    :return: IAM Policy for specified bucket
    """
    try:
        req = storage.buckets().getIamPolicy(bucket=bucket)
        res = req.execute()
        return res
    except HttpError as e:
        reason = compute._get_error_reason(e)
        if reason == 'notFound':
            logger.debug(
                ("The bucket %s was not found - returned a 404 not found error."
                 "Full details: %s"), bucket, e, )
            return None
        elif reason == 'forbidden':
            logger.debug(
                ("You do not have storage.bucket.getIamPolicy access to the bucket %s. "
                 "Full details: %s"), bucket, e, )
            return None
        else:
            raise
            

def transform_gcp_bucket_iam_policy(iam_res): 
    '''
    Transform the GCP Storage Bucket IAM Policy Resource for Neo4j Ingestion. 
    
    :type iam_res: IAM Policy Object 
    :param iam_res: The IAM Policy Resource associated with a GCP Bucket 
    
    :rtype: list of dict
    :return: List of roles and members corresponding to some storage bucket
    '''
    
    iam_list = [] 
    resource_id = iam_res['resourceId']
    bucket_id = resource_id.split('/')[-1] #resourceId is in the form 'projects/_/buckets/bucket_id' 
    
    
            
def get_gcp_buckets(storage, project_id):
    """
    Returns a list of storage objects within some given project

    :type storage: The GCP storage resource object
    :param storage: The storage resource object created by googleapiclient.discovery.build()

    :type project_id: str
    :param project_id: The Google Project Id that you are retrieving buckets from

    :rtype: Storage Object
    :return: Storage response object
    """
    try:
        req = storage.buckets().list(project=project_id)
        res = req.execute()
        return res
    except HttpError as e:
        reason = compute._get_error_reason(e)
        if reason == 'invalid':
            logger.warning(
                (
                    "The project %s is invalid - returned a 400 invalid error."
                    "Full details: %s"
                ),
                project_id,
                e,
            )
            return {}
        elif reason == 'forbidden':
            logger.warning(
                (
                    "You do not have storage.bucket.list access to the project %s. "
                    "Full details: %s"
                ), project_id, e, )
            return {}
        else:
            raise


def transform_gcp_buckets(bucket_res):
    '''
    Transform the GCP Storage Bucket response object for Neo4j ingestion

    :type bucket_res: The GCP storage resource object (https://cloud.google.com/storage/docs/json_api/v1/buckets)
    :param bucket_res: The return data

    :rtype: list of dict
    :return: List of buckets ready for ingestion to Neo4j
    '''

    bucket_list = []
    for b in bucket_res.get('items', []):
        bucket = {}
        bucket['etag'] = b.get('etag')
        bucket['iam_config_bucket_policy_only'] = \
            b.get('iamConfiguration', {}).get('bucketPolicyOnly', {}).get('enabled', None)
        bucket['id'] = b['id']
        bucket['labels'] = [(key, val) for (key, val) in b.get('labels', {}).items()]
        bucket['owner_entity'] = b.get('owner', {}).get('entity')
        bucket['owner_entity_id'] = b.get('owner', {}).get('entityId')
        bucket['kind'] = b.get('kind')
        bucket['location'] = b.get('location')
        bucket['location_type'] = b.get('locationType')
        bucket['meta_generation'] = b.get('metageneration', None)
        bucket['project_number'] = b['projectNumber']
        bucket['self_link'] = b.get('selfLink')
        bucket['storage_class'] = b.get('storageClass')
        bucket['time_created'] = b.get('timeCreated')
        bucket['updated'] = b.get('updated')
        bucket['versioning_enabled'] = b.get('versioning', {}).get('enabled', None)
        bucket['default_event_based_hold'] = b.get('defaultEventBasedHold', None)
        bucket['retention_period'] = b.get('retentionPolicy', {}).get('retentionPeriod', None)
        bucket['default_kms_key_name'] = b.get('encryption', {}).get('defaultKmsKeyName')
        bucket['log_bucket'] = b.get('logging', {}).get('logBucket')
        bucket['requester_pays'] = b.get('billing', {}).get('requesterPays', None)
        bucket_list.append(bucket)
    return bucket_list


def load_gcp_buckets(neo4j_session, buckets, gcp_update_tag):
    '''
    Ingest GCP Storage Buckets to Neo4j

    :type neo4j_session: Neo4j session object
    :param neo4j session: The Neo4j session object

    :type buckets: list
    :param buckets: List of GCP Storage Buckets to injest

    :type gcp_update_tag: timestamp
    :param gcp_update_tag: The timestamp value to set our new Neo4j nodes with

    :rtype: NoneType
    :return: Nothing
    '''

    query = """
    MERGE(p:GCPProject{projectnumber:{ProjectNumber}})
    ON CREATE SET p.firstseen = timestamp()
    SET p.lastupdated = {gcp_update_tag}

    MERGE(bucket:GCPBucket{id:{BucketId}})
    ON CREATE SET bucket.firstseen = timestamp(),
    bucket.bucket_id = {BucketId}
    SET bucket.self_link = {SelfLink},
    bucket.project_number = {ProjectNumber},
    bucket.kind = {Kind},
    bucket.location = {Location},
    bucket.location_type = {LocationType},
    bucket.labels = {Labels},
    bucket.meta_generation = {MetaGeneration},
    bucket.storage_class = {StorageClass},
    bucket.time_created = {TimeCreated},
    bucket.retention_period = {RetentionPeriod},
    bucket.iam_config_bucket_policy_only = {IamConfigBucketPolicyOnly},
    bucket.owner_entity = {OwnerEntity},
    bucket.owner_entity_id = {OwnerEntityId},
    bucket.lastupdated = {gcp_update_tag},
    bucket.versioning_enabled = {VersioningEnabled},
    bucket.log_bucket = {LogBucket},
    bucket.requester_pays = {RequesterPays},
    bucket.default_kms_key_name = {DefaultKmsKeyName}

    MERGE (p)-[r:RESOURCE]->(bucket)
    ON CREATE SET r.firstseen = timestamp()
    SET r.lastupdated = {gcp_update_tag}
    """
    for bucket in buckets:
        neo4j_session.run(
            query,
            ProjectNumber=bucket['project_number'],
            BucketId=bucket['id'],
            SelfLink=bucket['self_link'],
            Labels=bucket['labels'],
            Kind=bucket['kind'],
            Location=bucket['location'],
            LocationType=bucket['location_type'],
            MetaGeneration=bucket['meta_generation'],
            StorageClass=bucket['storage_class'],
            TimeCreated=bucket['time_created'],
            RetentionPeriod=bucket['retention_period'],
            IamConfigBucketPolicyOnly=bucket['iam_config_bucket_policy_only'],
            OwnerEntity=bucket['owner_entity'],
            OwnerEntityId=bucket['owner_entity_id'],
            VersioningEnabled=bucket['versioning_enabled'],
            LogBucket=bucket['log_bucket'],
            RequesterPays=bucket['requester_pays'],
            DefaultKmsKeyName=bucket['default_kms_key_name'],
            gcp_update_tag=gcp_update_tag,
        )


def cleanup_gcp_buckets(neo4j_session, common_job_parameters):
    """
    Delete out-of-date GCP Storage Bucket nodes and relationships

    :type neo4j_session: The Neo4j session object
    :param neo4j_session: The Neo4j session

    :type common_job_parameters: dict
    :param common_job_parameters: Dictionary of other job parameters to pass to Neo4j

    :rtype: NoneType
    :return: Nothing
    """
    run_cleanup_job('gcp_storage_bucket_cleanup.json', neo4j_session, common_job_parameters)


def sync_gcp_buckets(neo4j_session, storage, project_id, gcp_update_tag, common_job_parameters):
    """
    Get GCP instances using the Storage resource object, ingest to Neo4j, and clean up old data.

    :type neo4j_session: The Neo4j session object
    :param neo4j_session: The Neo4j session

    :type storage: The storage resource object created by googleapiclient.discovery.build()
    :param storage: The GCP Storage resource object

    :type project_id: str
    :param project_id: The project ID of the corresponding project

    :type gcp_update_tag: timestamp
    :param gcp_update_tag: The timestamp value to set our new Neo4j nodes with

    :type common_job_parameters: dict
    :param common_job_parameters: Dictionary of other job parameters to pass to Neo4j

    :rtype: NoneType
    :return: Nothing
    """
    storage_res = get_gcp_buckets(storage, project_id)
    bucket_list = transform_gcp_buckets(storage_res)
    load_gcp_buckets(neo4j_session, bucket_list, gcp_update_tag)
    cleanup_gcp_buckets(neo4j_session, common_job_parameters)
