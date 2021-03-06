import sys, os, time, glob
import aztk.models
import aztk.spark
import json
from aztk.spark.models import ClusterConfiguration, UserConfiguration
from azure.batch.models import BatchErrorException
from pprint import pprint
from aztk.error import AztkError
from azure.storage.table import TableService, Entity, TablePermissions

class AztkCluster:
    def __init__(self, vm_count = 0, sku_type = 'standard_d2_v2', username = 'admin', password = 'admin'):
        self.vm_count = vm_count
        self.sku_type = sku_type
        self.username = username
        self.password = password
        BATCH_ACCOUNT_NAME = os.environ['BATCH_ACCOUNT_NAME']
        BATCH_ACCOUNT_KEY = os.environ['BATCH_ACCOUNT_KEY']
        BATCH_SERVICE_URL = os.environ['BATCH_ACCOUNT_URL']
        STORAGE_ACCOUNT_SUFFIX = 'core.windows.net'
        self.STORAGE_ACCOUNT_NAME = os.environ['STORAGE_ACCOUNT_NAME']
        self.STORAGE_ACCOUNT_KEY = os.environ['STORAGE_ACCOUNT_KEY']

        self.secrets_confg = aztk.spark.models.SecretsConfiguration(
            shared_key=aztk.models.SharedKeyConfiguration(
            batch_account_name = BATCH_ACCOUNT_NAME,
            batch_account_key = BATCH_ACCOUNT_KEY,
            batch_service_url = BATCH_SERVICE_URL,
            storage_account_name = self.STORAGE_ACCOUNT_NAME,
            storage_account_key = self.STORAGE_ACCOUNT_KEY,
            storage_account_suffix = STORAGE_ACCOUNT_SUFFIX
            ),

        ssh_pub_key=""
        )
        self.table_service = TableService(account_name=self.STORAGE_ACCOUNT_NAME, account_key=self.STORAGE_ACCOUNT_KEY)

    def createCluster(self):


        # create a client
        client = aztk.spark.Client(self.secrets_confg)

        # list available clusters
        clusters = client.list_clusters()

        SPARK_CONFIG_PATH = os.path.normpath(os.path.join(os.path.dirname(__file__), 'spark', 'spark', '.config'))
        SPARK_JARS_PATH = os.path.normpath(os.path.join(os.path.dirname(__file__), 'spark','spark', 'jars'))

        SPARK_CORE_SITE = os.path.join(SPARK_CONFIG_PATH, 'core-site.xml')

        jars = glob.glob(os.path.join(SPARK_JARS_PATH, '*.jar'))

        # define spark configuration
        spark_conf = aztk.spark.models.SparkConfiguration(
            spark_defaults_conf=os.path.join(SPARK_CONFIG_PATH, 'spark-defaults.conf'),
            spark_env_sh=os.path.join(SPARK_CONFIG_PATH, 'spark-env.sh'),
            core_site_xml=SPARK_CORE_SITE,
            jars=jars
        )

        jupyterCustomScript = aztk.models.CustomScript("jupyter", "D:/home/site/wwwroot/flask/spark/customScripts/jupyter.sh", "all-nodes")        
        azuremlProjectFileShare = aztk.models.FileShare(self.STORAGE_ACCOUNT_NAME, self.STORAGE_ACCOUNT_KEY, 'azureml-project', '/mnt/azureml-project')
        azuremlFileShare = aztk.models.FileShare(self.STORAGE_ACCOUNT_NAME, self.STORAGE_ACCOUNT_KEY, 'azureml-share', '/mnt/azureml-share')
        # configure my cluster
        cluster_config = aztk.spark.models.ClusterConfiguration(
            docker_repo='aztk/python:spark2.2.0-python3.6.2-base',
            cluster_id="predictive-maintenance", # Warning: this name must be a valid Azure Blob Storage container name
            vm_count=self.vm_count,
            # vm_low_pri_count=2, #this and vm_count are mutually exclusive
            vm_size=self.sku_type,
            custom_scripts=[jupyterCustomScript],
            spark_configuration=spark_conf,
            file_shares=[azuremlProjectFileShare, azuremlFileShare],
            user_configuration=UserConfiguration(
                username=self.username,
                password=self.password,
            )
        )

        cluster = client.create_cluster(cluster_config)
        
        clusterDetails = {'PartitionKey': 'predictivemaintenance', 'RowKey': 'predictivemaintenance', 'Status': 'Provisioning', 'UserName': self.username}
        self.table_service.insert_or_merge_entity('cluster', clusterDetails)

    def getCluster(self):
        # create a client
        client = aztk.spark.Client(self.secrets_confg)
        clusterDetails = self.table_service.get_entity('cluster', 'predictivemaintenance', 'predictivemaintenance')
        try:
            cluster = client.get_cluster(cluster_id="predictive-maintenance")
            if clusterDetails.Status == 'Deleting':
                return clusterDetails
            for node in cluster.nodes:
                    remote_login_settings = client.get_remote_login_settings(cluster.id, node.id)
                    if node.id == cluster.master_node_id:
                        master_ipaddress = remote_login_settings.ip_address
                        master_Port = remote_login_settings.port
                        clusterDetails = {'PartitionKey': 'predictivemaintenance', 'RowKey': 'predictivemaintenance', 'Status': 'Provisioned', 'Master_Ip_Address': master_ipaddress, 'Master_Port': master_Port, 'UserName': clusterDetails.UserName}
                        self.table_service.insert_or_merge_entity('cluster', clusterDetails)
        
        except (AztkError, BatchErrorException):
                    if clusterDetails.Status == 'Deleting':
                        clusterDetails = {'PartitionKey': 'predictivemaintenance', 'RowKey': 'predictivemaintenance', 'Status': 'Not Created'}
                        self.table_service.insert_or_merge_entity('cluster', clusterDetails)               
    
        clusterDetails = self.table_service.get_entity('cluster', 'predictivemaintenance', 'predictivemaintenance')

        return clusterDetails

    def deleteCluster(self):

        clusterDetails = {'PartitionKey': 'predictivemaintenance', 'RowKey': 'predictivemaintenance', 'Status': 'Deleting'}
        self.table_service.insert_or_merge_entity('cluster', clusterDetails)
        # create a client
        client = aztk.spark.Client(self.secrets_confg)
        client.delete_cluster(cluster_id = "predictive-maintenance")
        
if __name__ == '__main__':
    pass
