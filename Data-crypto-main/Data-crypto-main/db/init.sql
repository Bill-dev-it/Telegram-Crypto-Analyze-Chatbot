-- Kích hoạt extension pgcrypto để sử dụng UUID
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Đảm bảo mã hóa dữ liệu đầu vào/ra của client là UTF-8 (hỗ trợ hoàn toàn tiếng Việt)
SET client_encoding = 'UTF8';

-- 1. Bảng Users: Lưu trữ thông tin phân hạng của người dùng bot Telegram
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    telegram_id BIGINT UNIQUE NOT NULL, -- Chuyển sang BIGINT lưu trực tiếp số ID, tiết kiệm RAM và tăng tốc Index đáng kể so với chuỗi
    package_type VARCHAR(20) NOT NULL DEFAULT 'Free',
    join_date TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Sử dụng B-Tree Index cho cấu trúc tìm kiếm exact match theo mảng số nguyên BIGINT, tối ưu độ trễ cho cực nhiều request cùng lúc
CREATE INDEX IF NOT EXISTS idx_users_telegram_id ON users USING btree(telegram_id);


-- 2. Bảng Tokens: Lưu trữ cấu trúc Data từ Blockchain
CREATE TABLE IF NOT EXISTS tokens (
    contract_address VARCHAR(42) PRIMARY KEY, -- VARCHAR(42) là chuẩn tối ưu tuyệt đối cho độ dài của địa chỉ ví dạng 0x + 40 ký tự hex
    name VARCHAR(255) NOT NULL,
    symbol VARCHAR(50) NOT NULL,
    network VARCHAR(50) NOT NULL DEFAULT 'Ethereum',
    risk_score NUMERIC(5, 2),
    last_scanned_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Bổ sung composite index (Network + Time) để tối ưu các lệnh truy xuất danh sách token sắp xếp theo thứ tự quét gần nhất
CREATE INDEX IF NOT EXISTS idx_tokens_network_scanned ON tokens(network, last_scanned_at DESC);


-- 3. Bảng ScanHistory: Lưu kết quả phân tích AI trả về
CREATE TABLE IF NOT EXISTS scan_history (
    id SERIAL PRIMARY KEY, -- SERIAL tự tăng theo đúng yêu cầu (nhẹ hơn UUID, tối ưu lưu trữ log lịch sử liên tục)
    user_id UUID NOT NULL,
    token_address VARCHAR(42) NOT NULL,
    result_json JSONB NOT NULL, -- Cực kỳ bám sát Technical Spec: JSONB tối ưu Binary Tree, hỗ trợ xử lý tìm kiếm nội suy JSON thần tốc
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_token FOREIGN KEY (token_address) REFERENCES tokens(contract_address) ON DELETE CASCADE
);

-- Các Index Foreign Keys bắt buộc phải có để truy vấn JOIN giữa các bảng với lưu lượng 10,000 rps không bị thắt cổ chai (bottleneck)
CREATE INDEX IF NOT EXISTS idx_scan_history_user_id ON scan_history(user_id);
CREATE INDEX IF NOT EXISTS idx_scan_history_token_address ON scan_history(token_address);

-- Tạo GIN Index (Generalized Inverted Index) chuyên dụng siêu cấp cho JSONB để quét được cả Key/Value linh động bên trong cục Data (nếu cần)
CREATE INDEX IF NOT EXISTS idx_scan_history_result_json ON scan_history USING GIN (result_json);
