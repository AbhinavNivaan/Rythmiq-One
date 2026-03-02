import os
import uuid
import base64
import subprocess
from io import BytesIO

import boto3
import requests
from PIL import Image
from botocore.config import Config
from botocore.exceptions import ClientError
from dotenv import load_dotenv

load_dotenv('.env')

endpoint = os.environ['DO_SPACES_ENDPOINT']
region = os.environ['DO_SPACES_REGION']
bucket = os.environ['DO_SPACES_BUCKET']
access_key = os.environ['DO_SPACES_ACCESS_KEY']
secret_key = os.environ['DO_SPACES_SECRET_KEY']
worker_url = os.environ['CLOUD_RUN_WORKER_URL'].rstrip('/')

s3 = boto3.client(
    's3',
    endpoint_url=endpoint,
    region_name=region,
    aws_access_key_id=access_key,
    aws_secret_access_key=secret_key,
    config=Config(signature_version='s3v4'),
)

job_id = str(uuid.uuid4())
user_id = str(uuid.uuid4())
raw_path = f"uploads/{user_id}/{job_id}/test.png"
master_path = f"master/{user_id}/{job_id}/master.bin"
preview_path = f"preview/{user_id}/{job_id}/preview.jpg"

buffer = BytesIO()
Image.new('RGB', (32, 32), color=(255, 255, 255)).save(buffer, format='PNG')
png = buffer.getvalue()

s3.put_object(Bucket=bucket, Key=raw_path, Body=png, ContentType='image/png')

sek_b64 = base64.b64encode(os.urandom(32)).decode('ascii')

payload = {
    'job_id': job_id,
    'user_id': user_id,
    'sek_b64': sek_b64,
    'portal_schema': {
        'id': str(uuid.uuid4()),
        'name': 'direct_worker_test',
        'version': 1,
        'schema_definition': {
            'target_width': 100,
            'target_height': 100,
            'target_dpi': 300,
            'max_kb': 200,
            'filename_pattern': '{job_id}',
            'output_format': 'jpeg',
            'quality': 85,
        },
    },
    'input': {
        'raw_path': raw_path,
        'mime_type': 'image/png',
        'original_filename': 'test.png',
    },
    'storage': {
        'bucket': bucket,
        'region': region,
        'endpoint': endpoint,
    },
    'output': {
        'master_path': master_path,
        'preview_path': preview_path,
    },
}

id_token = subprocess.check_output(['gcloud', 'auth', 'print-identity-token'], text=True).strip()
response = requests.post(
    worker_url + '/process',
    json=payload,
    headers={'Authorization': f'Bearer {id_token}'},
    timeout=180,
)

print('worker_status_code', response.status_code)
print('worker_response', response.text[:500])
response_json = response.json() if response.headers.get('content-type', '').startswith('application/json') else {}

raw_deleted = False
try:
    s3.head_object(Bucket=bucket, Key=raw_path)
except ClientError as error:
    code = error.response.get('Error', {}).get('Code')
    raw_deleted = code in ('404', 'NoSuchKey', 'NotFound')

master_exists = False
master_differs = False
returned_master_path = None
try:
    returned_master_path = (
        response_json.get('output', {})
        .get('artifacts', {})
        .get('master_path')
    )
except Exception:
    returned_master_path = None

try:
    master_key = returned_master_path or master_path
    master_data = s3.get_object(Bucket=bucket, Key=master_key)['Body'].read()
    master_exists = True
    master_differs = master_data != png
except Exception:
    pass

print('job_id', job_id)
print('raw_deleted', raw_deleted)
print('master_exists', master_exists)
print('master_differs_from_raw', master_differs)

ok = response.status_code == 200 and raw_deleted and master_exists and master_differs
print('E2E_DIRECT_WORKER_TEST', 'PASS' if ok else 'FAIL')
if not ok:
    raise SystemExit(2)
