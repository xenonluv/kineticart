/** @type {import('next').NextConfig} */
const nextConfig = {
  // 단일 실행파일(server.js)로 빌드 → Docker 이미지 경량화 + 어디든 이식
  output: "standalone",
};

export default nextConfig;
