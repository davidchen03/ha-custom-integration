# VU AWS S3 整合元件

這是一個自訂的 Home Assistant 整合元件，基於官方的 [AWS S3 元件](https://github.com/home-assistant/core/tree/dev/homeassistant/components/aws_s3)進行修改，增加了對儲存桶內特定資料夾（path）的支援，使您能更有彈性地組織和管理 S3 中的檔案。

## 功能特色

- 🔐 從 Home Assistant 安全地連接到 AWS S3 或任何相容的 S3 服務
- 📁 支援指定儲存桶內的特定資料夾/路徑做為基礎目錄
- 💾 支援 Home Assistant 備份功能 - 將您的備份直接儲存到 S3
- 📤 提供服務 API 讓您可以上傳、下載、刪除和列出 S3 檔案

## 與官方 AWS S3 整合元件的差異

本整合元件在官方 AWS S3 整合元件的基礎上增加了以下功能：

- **資料夾支援**：可以指定儲存桶內的子目錄路徑作為基礎路徑
- **相對路徑**：所有檔案操作都可以使用相對於配置的基礎路徑的相對路徑
- **優化的檔案管理**：更便捷地在指定資料夾內組織和管理檔案

## 安裝方式

### 使用 HACS (推薦)

1. 確保您已安裝 [HACS (Home Assistant Community Store)](https://hacs.xyz/)
2. 點擊 HACS > 整合元件 > 右上角三點圖示 > 自訂存儲庫
3. 新增此存儲庫 URL 並選擇類別為「整合元件」
4. 點擊「+ 探索並下載存儲庫」並搜尋 "VU AWS S3"
5. 點擊下載，完成後重新啟動 Home Assistant

### 手動安裝

1. 下載此存儲庫的 ZIP 檔案
2. 解壓縮並將 `custom_components/vu_aws_s3` 目錄複製到您的 Home Assistant 的 `custom_components` 目錄中
3. 重新啟動 Home Assistant

## 設定方式

### 前置準備

1. 在 AWS 中創建一個 IAM 使用者，並至少授予以下權限:

   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Effect": "Allow",
         "Action": [
           "s3:ListBucket",
           "s3:GetObject",
           "s3:PutObject",
           "s3:DeleteObject"
         ],
         "Resource": [
           "arn:aws:s3:::your-bucket-name",
           "arn:aws:s3:::your-bucket-name/*"
         ]
       }
     ]
   }
   ```

2. 記下 IAM 使用者的存取金鑰 ID 和秘密存取金鑰

### 在 Home Assistant 中設定

1. 在 Home Assistant 中，前往 **設定** > **裝置與服務** > **整合元件** > **新增整合元件**
2. 搜尋 "VU AWS S3" 並選擇它
3. 輸入以下資訊:
   - **Access Key ID**: 您的 AWS 存取金鑰 ID
   - **Secret Access Key**: 您的 AWS 秘密存取金鑰
   - **Bucket**: S3 儲存桶名稱
   - **Endpoint URL**: S3 端點 URL (預設為 `https://s3.eu-central-1.amazonaws.com/`)
   - **Folder Path (optional)**: 儲存桶內的資料夾路徑 (可選，不需要開頭的 `/`)

## 使用方式

### 備份功能

一旦設定完成，VU AWS S3 整合元件會自動顯示在 Home Assistant 的備份選項中。

1. 前往 **設定** > **系統** > **備份**
2. 點選 **建立備份**
3. 在 **儲存位置** 下拉選單中選擇 **VU AWS S3**
4. 完成其他備份設定，並點擊 **建立**

## 致謝

本專案基於 [Home Assistant AWS S3 整合元件](https://github.com/home-assistant/core/tree/dev/homeassistant/components/aws_s3) 進行修改和擴展。感謝原始開發者的貢獻。
