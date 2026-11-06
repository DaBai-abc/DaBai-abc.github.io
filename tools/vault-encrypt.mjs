#!/usr/bin/env node
/**
 * 工具箱密文页 · 加解密工具
 *
 * tools/index.html 的页面本体是密文，浏览器端用 WebCrypto 解密：
 *   PBKDF2-SHA256（250000 轮）派生 256 位密钥 → AES-256-GCM
 * 本脚本用 Node 内置 crypto 做同一套运算，参数严格对齐，改完页面要重新加密。
 *
 * 用法
 * ----
 *   解密到明文：
 *     node tools/vault-encrypt.mjs decrypt <口令> tools/vault.plain.html
 *
 *   明文改完，重新加密写回页面：
 *     node tools/vault-encrypt.mjs encrypt <口令> tools/vault.plain.html
 *
 * 口令只从命令行读，不写进任何文件。盐和 IV 每次加密都重新随机生成，
 * 所以同一份明文每次加密得到的密文都不同，属于正常现象。
 *
 * 为什么不能直接改 index.html
 * --------------------------
 * 页面里那段 <script id="vault-data"> 是密文，直接改里面的字等于把密文改坏，
 * 浏览器解不开，会一直停在「口令不对」。必须解出明文、改明文、再加密回去。
 */

import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';

const ITER = 250000;
const PAGE = path.resolve(process.cwd(), 'tools/index.html');
const SCRIPT_RE = /(<script id="vault-data" type="application\/json">)(.*?)(<\/script>)/s;

function readPage() {
  const html = fs.readFileSync(PAGE, 'utf8');
  const m = html.match(SCRIPT_RE);
  if (!m) throw new Error('tools/index.html 里没找到 vault-data');
  return { html, data: JSON.parse(m[2].trim()) };
}

function deriveKey(pw, salt, iter) {
  return crypto.pbkdf2Sync(Buffer.from(pw, 'utf8'), salt, iter, 32, 'sha256');
}

function decrypt(pw, data) {
  const raw = Buffer.from(data.ct, 'base64');
  const decipher = crypto.createDecipheriv('aes-256-gcm', deriveKey(pw, Buffer.from(data.salt, 'base64'), data.iter), Buffer.from(data.iv, 'base64'));
  decipher.setAuthTag(raw.subarray(raw.length - 16));
  const json = Buffer.concat([decipher.update(raw.subarray(0, raw.length - 16)), decipher.final()]).toString('utf8');
  return JSON.parse(json);
}

function encrypt(pw, obj, meta) {
  const salt = crypto.randomBytes(16);
  const iv = crypto.randomBytes(12);
  const cipher = crypto.createCipheriv('aes-256-gcm', deriveKey(pw, salt, meta.iter), iv);
  const body = Buffer.concat([cipher.update(JSON.stringify(obj), 'utf8'), cipher.final()]);
  return {
    v: meta.v,
    iter: meta.iter,
    salt: salt.toString('base64'),
    iv: iv.toString('base64'),
    ct: Buffer.concat([body, cipher.getAuthTag()]).toString('base64'),
    id: meta.id,
    lock: meta.lock,
    built: new Date().toISOString().slice(0, 10),
    bytes: body.length,
  };
}

const [action, pw, outPath] = process.argv.slice(2);
if (!action || !pw) {
  console.error('用法: node tools/vault-encrypt.mjs <decrypt|encrypt> <口令> [明文文件路径]');
  process.exit(1);
}

const { html, data } = readPage();

if (action === 'decrypt') {
  const obj = decrypt(pw, data);
  const target = outPath || 'tools/vault.plain.html';
  fs.writeFileSync(target, obj.html, 'utf8');
  console.log(`已解密 → ${target}（${Buffer.byteLength(obj.html, 'utf8')} 字节，kind=${obj.kind}）`);
} else if (action === 'encrypt') {
  const src = outPath || 'tools/vault.plain.html';
  if (!fs.existsSync(src)) throw new Error(`明文文件不存在: ${src}，先跑 decrypt`);
  const obj = { kind: 'html', html: fs.readFileSync(src, 'utf8') };
  const next = encrypt(pw, obj, data);
  const payload = JSON.stringify(next);
  fs.writeFileSync(PAGE, html.replace(SCRIPT_RE, (_m, a, _b, c) => a + payload + c), 'utf8');
  console.log(`已加密写回 ${PAGE}（ct ${next.ct.length} 字符，built ${next.built}）`);
  console.log('提醒：明文文件别提交进仓库，改完删掉或加进 .gitignore。');
} else {
  console.error(`未知动作: ${action}`);
  process.exit(1);
}
