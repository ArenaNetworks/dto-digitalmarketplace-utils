import os
import re
import boto3
import botocore
from werkzeug.utils import secure_filename
from flask import current_app
from io import BytesIO


def allowed_file(filename):
    return filename.lower().rsplit('.', 1)[1] in current_app.config.get('ALLOWED_EXTENSIONS')


def s3_generate_unique_filename(filename, path):
    file_exists = False
    try:
        next(s3_download_file(current_app.config.get('S3_BUCKET_NAME'), filename, path))
        file_exists = True
    except botocore.exceptions.ClientError as e:
        pass
    if file_exists:
        filename_part = filename.rsplit('.', 1)[0]
        ext_part = filename.rsplit('.', 1)[1]
        number = 2
        matches = re.match(r'(.+?)_(\d{1,})$', filename_part)
        if matches:
            filename_part = matches.group(1)
            number = int(matches.group(2)) + 1
        filename = '%s_%s.%s' % (filename_part, number, ext_part)
        return s3_generate_unique_filename(filename, path)
    else:
        return filename


def s3_upload_file_from_request(request, key, path=''):
    if not request.files:
        raise Exception('No files in request')

    fileObj = request.files.get(key)

    if not fileObj:
        raise Exception('Invalid request.files key')

    return s3_upload_fileObj(fileObj, path)


def s3_upload_fileObj(fileObj, path=''):
    if not allowed_file(fileObj.filename):
        raise Exception('Invalid file extension: {}'.format(fileObj.filename))

    filename = secure_filename(fileObj.filename)
    s3 = boto3.resource(
        's3',
        endpoint_url=os.getenv('AWS_S3_URL')
    )
    bucket = s3.Bucket(current_app.config.get('S3_BUCKET_NAME'))

    filename = s3_generate_unique_filename(filename, path)

    bucket.upload_fileobj(fileObj, os.path.join(path, filename))

    return filename


def s3_download_file(bucket_name, file, path):
    filename = secure_filename(file)
    s3 = boto3.client(
        's3',
        endpoint_url=os.getenv('AWS_S3_URL')
    )
    obj = s3.get_object(Bucket=bucket_name, Key=os.path.join(path, filename))
    body = obj['Body']
    for chunk in body.iter_chunks(chunk_size=10 * 1024):
        yield chunk
