import pytest
import mock
import botocore
from dmutils.config import init_app
from dmutils.file import (
    s3_upload_fileObj, s3_upload_file_from_request, s3_download_file, s3_generate_unique_filename
)


@pytest.fixture
def s3_resource():
    with mock.patch('boto3.resource') as boto_resource:
        instance = boto_resource.return_value
        yield instance


@pytest.fixture
def file_app(app):
    init_app(app)
    app.config['ALLOWED_EXTENSIONS'] = ['pdf']
    app.config['S3_BUCKET_NAME'] = ['testbucket']
    yield app


@mock.patch('dmutils.file.s3_download_file')
def test_s3_upload_with_correct_params(s3_download_file, file_app, s3_resource):
    with file_app.app_context():
        fileObj = mock.MagicMock()
        fileObj.filename = "test.pdf"
        s3_download_file.side_effect = botocore.exceptions.ClientError({'Error': {}}, '')
        s3_upload_fileObj(fileObj, 'path')

    s3_resource.Bucket().upload_fileobj.assert_called_once_with(
        fileObj,
        "path/test.pdf"
    )


def test_s3_upload_with_invalid_extension(file_app, s3_resource):
    with file_app.app_context():
        fileObj = mock.MagicMock()
        fileObj.filename = "test.txt"

        with pytest.raises(Exception):
            s3_upload_fileObj(fileObj, 'path')


@mock.patch('dmutils.file.s3_download_file')
def test_s3_upload_with_uppercase_extension(s3_download_file, file_app, s3_resource):
    with file_app.app_context():
        fileObj = mock.MagicMock()
        fileObj.filename = "TEST.PDF"
        s3_download_file.side_effect = botocore.exceptions.ClientError({'Error': {}}, '')
        s3_upload_fileObj(fileObj, 'path')

    s3_resource.Bucket().upload_fileobj.assert_called_once_with(
        fileObj,
        "path/TEST.PDF"
    )


def test_s3_upload_no_request_files():
    request = mock.MagicMock()
    request.files = None
    with pytest.raises(Exception):
        s3_upload_file_from_request(request, 'test')


def test_s3_upload_invalid_file_key():
    request = mock.MagicMock()
    request.files = {'key': 'value'}
    with pytest.raises(Exception):
        s3_upload_file_from_request(request, 'test')


@mock.patch('dmutils.file.s3_upload_fileObj')
def test_s3_upload_from_request(upload):
    request = mock.MagicMock()
    request.files = {'test': 'value'}
    s3_upload_file_from_request(request, 'test', 'path')

    upload.assert_called_once_with('value', 'path')


def test_s3_download_with_correct_params(file_app, s3_resource):
    with file_app.app_context():
        s3_download_file('file.txt', 'path')

    s3_resource.Bucket().download_fileobj.assert_called_once_with(
        'path/file.txt',
        mock.ANY
    )


@mock.patch('dmutils.file.s3_download_file')
def test_s3_upload_rename_instead_of_overwrite(s3_download_file, file_app, s3_resource):
    with file_app.app_context():
        fileObj = mock.MagicMock()
        fileObj.filename = "test.pdf"
        s3_download_file.side_effect = botocore.exceptions.ClientError({'Error': {}}, '')
        s3_upload_fileObj(fileObj, 'path')

    s3_resource.Bucket().upload_fileobj.assert_called_once_with(
        fileObj,
        "path/test.pdf"
    )

    with file_app.app_context():
        fileObj = mock.MagicMock()
        fileObj.filename = "test.pdf"
        s3_download_file.side_effect = [None, botocore.exceptions.ClientError({'Error': {}}, '')]
        s3_upload_fileObj(fileObj, 'path')

    s3_resource.Bucket().upload_fileobj.assert_called_with(
        fileObj,
        "path/test_2.pdf"
    )
