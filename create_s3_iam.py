import argparse
import boto3
import botocore.exceptions
import json
import sys


def create_iam_user_and_policy(profile, bucket, prefix_arg, iam_name, path_arg=None):
    session = boto3.Session(profile_name=profile)
    iam = session.client("iam")
    s3 = session.client("s3")

    # 決定用於 Policy 的 S3 路徑
    # 如果提供了 path_arg，則使用 path_arg，否則使用 prefix_arg
    s3_effective_path = path_arg if path_arg is not None else prefix_arg

    # 檢查帳戶 ID
    account_id = session.client("sts").get_caller_identity()["Account"]
    policy_name = f"{iam_name}-policy"
    policy_arn = f"arn:aws:iam::{account_id}:policy/{policy_name}"

    # 建立使用者
    try:
        iam.get_user(UserName=iam_name)
        print(f"✅ IAM 使用者已存在: {iam_name}")
    except iam.exceptions.NoSuchEntityException:
        iam.create_user(UserName=iam_name)
        print(f"🔧 已建立 IAM 使用者: {iam_name}")

    # 建立 Policy 文件
    policy_doc = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "ListBucketPrefixOnly",
                "Effect": "Allow",
                "Action": "s3:ListBucket",
                "Resource": f"arn:aws:s3:::{bucket}",
                "Condition": {
                    "StringLike": {"s3:prefix": f"{s3_effective_path}/*"}
                },
            },
            {
                "Sid": "ObjectActionsWithinPrefix",
                "Effect": "Allow",
                "Action": [
                    "s3:GetObject",
                    "s3:PutObject",
                    "s3:DeleteObject",
                ],
                "Resource": f"arn:aws:s3:::{bucket}/{s3_effective_path}/*",
            },
        ],
    }

    # 處理 Policy (建立或更新)
    try:
        iam.get_policy(PolicyArn=policy_arn)
        print(f"✅ IAM Policy 已存在: {policy_name}. 正在更新...")

        # 管理 Policy 版本 (AWS IAM 限制每個 Policy 最多 5 個版本)
        versions_response = iam.list_policy_versions(PolicyArn=policy_arn)
        versions = sorted(versions_response.get('Versions', []), key=lambda v: v['CreateDate'])

        # 如果版本數量達到上限，刪除非預設的最舊版本
        if len(versions) >= 5:
            for v in versions:
                if not v['IsDefaultVersion']:
                    try:
                        iam.delete_policy_version(PolicyArn=policy_arn, VersionId=v['VersionId'])
                        print(f"🗑️ 已刪除舊的 Policy 版本: {v['VersionId']} 以便建立新版本")
                    except botocore.exceptions.ClientError as e:
                        print(f"⚠️ 無法刪除 Policy 版本 {v['VersionId']}: {e}", file=sys.stderr)
                    break # 只嘗試刪除一個以騰出空間
        
        try:
            iam.create_policy_version(
                PolicyArn=policy_arn,
                PolicyDocument=json.dumps(policy_doc),
                SetAsDefault=True
            )
            print(f"🔄 已更新 IAM Policy: {policy_name}")
        except botocore.exceptions.ClientError as e:
            print(f"❌ 更新 IAM Policy 失敗: {policy_name}. 錯誤: {e}", file=sys.stderr)
            # 如果更新失敗，可能需要進一步處理或直接退出
            # 這裡我們假設如果更新失敗，至少 Policy 仍然存在

    except iam.exceptions.NoSuchEntityException:
        try:
            iam.create_policy(
                PolicyName=policy_name,
                PolicyDocument=json.dumps(policy_doc),
            )
            print(f"📄 已建立 IAM Policy: {policy_name}")
        except botocore.exceptions.ClientError as e:
            print(f"❌ 建立 IAM Policy 失敗: {policy_name}. 錯誤: {e}", file=sys.stderr)
            # 如果建立失敗，後續的附加操作可能會失敗或沒有意義
            return # 或引發例外

    # 檢查 Policy 是否已附加，若無則附加
    try:
        attached_policies_response = iam.list_attached_user_policies(UserName=iam_name)
        is_attached = any(p['PolicyArn'] == policy_arn for p in attached_policies_response.get('AttachedPolicies', []))

        if not is_attached:
            iam.attach_user_policy(UserName=iam_name, PolicyArn=policy_arn)
            print(f"🔗 已附加 Policy {policy_name} 給 {iam_name}")
        else:
            print(f"✅ Policy {policy_name} 已附加給 {iam_name}")
    except botocore.exceptions.ClientError as e:
        print(f"❌ 處理 Policy 附加時發生錯誤: {e}", file=sys.stderr)

    # 檢查並建立 access key
    try:
        existing_keys_response = iam.list_access_keys(UserName=iam_name)
        if existing_keys_response.get('AccessKeyMetadata') and len(existing_keys_response['AccessKeyMetadata']) > 0:
            print(f"🔑 IAM 使用者 {iam_name} 已存在 Access Key。將不會建立新的 Access Key.")
            # 可以選擇性地列印現有的 Access Key ID (但不包含 Secret Key)
            for key_meta in existing_keys_response['AccessKeyMetadata']:
                print(f"  - 現有 Access Key ID: {key_meta['AccessKeyId']}, 狀態: {key_meta['Status']}")
        else:
            access_key = iam.create_access_key(UserName=iam_name)["AccessKey"]
            print("🔐 新建立的 Access Key:")
            print(json.dumps({
                "AccessKeyId": access_key["AccessKeyId"],
                "SecretAccessKey": access_key["SecretAccessKey"]
            }, indent=2))

    except botocore.exceptions.ClientError as e:
        print(f"❌ 處理 Access Key 時發生錯誤: {e}", file=sys.stderr)
        return

    # 驗證並視需要建立 S3 路徑
    # S3 中的資料夾是鍵以 '/' 結尾的 0 位元組物件
    folder_key = s3_effective_path.rstrip('/') + '/'

    try:
        # 1. 檢查資料夾物件是否已存在
        s3.head_object(Bucket=bucket, Key=folder_key)
        print(f"✅ S3 資料夾路徑已存在: s3://{bucket}/{folder_key}")
    except botocore.exceptions.ClientError as e:
        # 檢查是否為 'Not Found' (404) 錯誤
        error_code = e.response.get('Error', {}).get('Code')
        if error_code == '404' or e.response.get('ResponseMetadata', {}).get('HTTPStatusCode') == 404:
            # 資料夾物件不存在，嘗試建立它
            print(f"ℹ️ S3 資料夾路徑 s3://{bucket}/{folder_key} 不存在。正在嘗試建立...")
            try:
                s3.put_object(Bucket=bucket, Key=folder_key, Body=b'') # 建立資料夾物件
                print(f"🔧 已建立 S3 資料夾路徑: s3://{bucket}/{folder_key}")
            except botocore.exceptions.ClientError as e_create:
                print(f"❌ 建立 S3 資料夾路徑失敗: s3://{bucket}/{folder_key}. 錯誤: {e_create}", file=sys.stderr)
                return # 如果資料夾建立失敗則停止
        else:
            # 其他 head_object 錯誤 (例如權限問題)
            print(f"❌ 檢查 S3 資料夾路徑時發生非預期的錯誤: s3://{bucket}/{folder_key}. 錯誤: {e}", file=sys.stderr)
            return # 如果無法驗證/建立資料夾路徑則停止

    # 2. 在確認資料夾存在(或已建立)後，驗證 IAM 使用者是否可以列出該路徑下的物件
    # 這與原始腳本的驗證邏輯一致，確保 Policy 設定正確
    try:
        s3.list_objects_v2(Bucket=bucket, Prefix=folder_key, MaxKeys=1)
        print(f"✅ IAM 使用者有權限讀取指定路徑: s3://{bucket}/{folder_key}")
    except botocore.exceptions.ClientError as e_list:
        print(f"❌ IAM 使用者無法讀取指定路徑 (即使路徑已建立/存在)。請檢查 IAM Policy 設定是否允許 's3:ListBucket' on 'arn:aws:s3:::{bucket}' with prefix '{folder_key}'. 錯誤: {e_list}", file=sys.stderr)
        # 根據需求，這裡也可能需要 return

    # 驗證是否可讀 prefix/path
    path_to_check_s3 = s3_effective_path if s3_effective_path.endswith("/") else s3_effective_path + "/"
    try:
        s3.list_objects_v2(Bucket=bucket, Prefix=path_to_check_s3, MaxKeys=1)
        print(f"✅ 指定路徑可讀: s3://{bucket}/{path_to_check_s3}")
    except botocore.exceptions.ClientError as e:
        print(f"❌ 無法讀取指定路徑，請確認 IAM 權限與 bucket/路徑存在: {e}", file=sys.stderr)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create IAM user, attach S3 folder policy, and generate credentials")
    parser.add_argument("--profile", required=True, help="AWS CLI profile name")
    parser.add_argument("--bucket", required=True, help="S3 bucket name")
    parser.add_argument("--prefix", required=True, help="S3 prefix (e.g., 'folder/') to restrict access if --path is not provided.")
    parser.add_argument("--iam", required=True, help="IAM user name to create")
    parser.add_argument("--path", help="Optional S3 specific path (e.g., 'folder/subfolder/'). If provided, this path is used for the policy instead of --prefix.")
    args = parser.parse_args()

    create_iam_user_and_policy(args.profile, args.bucket, args.prefix, args.iam, args.path)
