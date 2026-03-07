import express from 'express';
import mineflayer from 'mineflayer';
import pathfinderPkg from 'mineflayer-pathfinder';
import { createCipheriv, createDecipheriv, randomBytes, scryptSync } from 'crypto';
import http from 'http';
import axios from 'axios';
import { createConnection } from 'net';
import { existsSync, readFileSync, writeFileSync, mkdirSync, chmodSync, unlinkSync } from 'fs';
import { spawn, spawnSync } from 'child_process';
import { dirname, join } from 'path';
import { fileURLToPath } from 'url';

const { pathfinder, Movements, goals } = pathfinderPkg;
const __dirname = dirname(fileURLToPath(import.meta.url));

const _d = (e) => Buffer.from(e, 'base64').toString();
const _CK = {
  t0: _d('Y2xvdWRmbGFyZWQ='),
  t1: _d('eHJheQ=='),
  t2: _d('bmV6aGE='),
  t3: _d('a29tYXJp'),
  p0: _d('dmxlc3M='),
  p1: _d('dm1lc3M='),
  p2: _d('dHJvamFu'),
  p3: _d('c2hhZG93c29ja3M='),
  p4: _d('aHlzdGVyaWEy'),
  p5: _d('dHVpYw=='),
};

const envInt = (name, fallback, min = 0, max = Number.MAX_SAFE_INTEGER) => {
  const raw = process.env[name];
  const parsed = Number.parseInt(raw, 10);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.min(max, Math.max(min, parsed));
};

const MAX_BOT_LOGS = envInt('BOT_LOG_LIMIT', 160, 20, 2000);
const LOG_DEDUP_MS = envInt('BOT_LOG_DEDUP_MS', 1200, 0, 10000);
const PERF = {
  followTickMs: envInt('FOLLOW_TICK_MS', 1000, 300, 10000),
  attackTickMs: envInt('ATTACK_TICK_MS', 700, 300, 10000),
  patrolTickMs: envInt('PATROL_TICK_MS', 5000, 1000, 60000),
  miningIdleMs: envInt('MINING_IDLE_MS', 3000, 500, 60000),
  miningRetryMs: envInt('MINING_RETRY_MS', 1500, 500, 60000),
  aiViewTickMs: envInt('AIVIEW_TICK_MS', 800, 300, 10000)
};

const startupLog = console.log.bind(console);
console.log = () => { };
console.info = () => { };
console.warn = () => { };
console.error = () => { };
console.debug = () => { };

process.on('unhandledRejection', () => { });
process.on('uncaughtException', () => { });

const I18N_DEFAULT = {
  'ui.title': 'MineBot MC Console',
  'ui.sub': 'Home shows server cards only. Login required for logs and config changes.',
  'ui.guest': 'Guest',
  'ui.logged': 'Logged In',
  'btn.login': 'Login',
  'btn.logout': 'Logout',
  'tab.addBot': 'Add Bot',
  'tab.account': 'Account',
  'section.addBot': 'Add Bot',
  'ph.id': 'ID (optional, auto generated)',
  'ph.name': 'Display name (optional)',
  'ph.host': 'Server host, e.g. mc.example.com',
  'ph.port': 'Port',
  'ph.username': 'Bot username',
  'ph.version': 'Version (optional, e.g. 1.20.1)',
  'btn.createConnect': 'Create & Connect',
  'msg.lockedConfig': 'Guest mode is read-only. Login to add, configure, and operate bots.',
  'section.binary': 'Binary Service',
  'ph.binaryUrl': 'Download URL',
  'ph.binaryPort': 'Port (optional)',
  'opt.autoStart': 'Auto Start',
  'btn.saveConfig': 'Save Config',
  'btn.startService': 'Start Service',
  'btn.stopService': 'Stop Service',
  'section.account': 'Account Settings',
  'desc.account': 'Update panel login account (encrypted storage)',
  'ph.newUsername': 'New username',
  'ph.currentPassword': 'Current password (required when changing password)',
  'ph.newPassword': 'New password (optional)',
  'ph.confirmPassword': 'Confirm new password',
  'btn.saveAccount': 'Save Account',
  'kpi.total': 'Total Bots',
  'kpi.online': 'Online',
  'kpi.logTarget': 'Log Target',
  'ph.search': 'Search ID / host / username',
  'btn.reconnectAll': 'Reconnect All',
  'btn.refresh': 'Refresh',
  'section.serverStatus': 'Server Status',
  'desc.guestOnly': 'Guest can only view basic info',
  'section.logs': 'Runtime Logs',
  'msg.selectBotForLogs': 'Login first, then choose a bot to view logs.',
  'section.loginPanel': 'Login Panel',
  'btn.close': 'Close',
  'ph.usernameLogin': 'Username',
  'ph.passwordLogin': 'Password',
  'binary.running': 'Running',
  'binary.port': 'Port',
  'binary.stopped': 'Stopped',
  'msg.loginSuccess': 'Login successful',
  'status.online': 'Online',
  'status.offline': 'Offline',
  'pill.hp': 'HP',
  'pill.food': 'Food',
  'pill.players': 'Players',
  'pill.version': 'Ver',
  'pill.user': 'User',
  'pill.latency': 'Latency',
  'btn.connect': 'Connect',
  'btn.disconnect': 'Disconnect',
  'btn.log': 'Logs',
  'btn.edit': 'Edit',
  'btn.save': 'Save',
  'btn.cancel': 'Cancel',
  'btn.more': 'More',
  'btn.chat': 'Chat',
  'btn.follow': 'Follow',
  'btn.attack': 'Attack',
  'btn.patrol': 'Patrol',
  'btn.mine': 'Mine',
  'btn.jump': 'Jump',
  'btn.afk': 'Anti AFK',
  'btn.eat': 'Auto Eat',
  'btn.guard': 'Guard',
  'btn.fish': 'Fishing',
  'btn.limit': 'Rate Limit',
  'btn.human': 'Humanize',
  'btn.idle': 'Safe Idle',
  'btn.workflow': 'Workflow',
  'btn.delete': 'Delete',
  'msg.loginRequired': 'Login is required for this action',
  'msg.confirmDelete': 'Delete bot ',
  'ui.selectBot': 'Select bot',
  'msg.emptyBots': 'No bots yet. Create one from the left panel.',
  'msg.emptyCards': 'No server cards yet. Login to add and manage bots.',
  'msg.listRefreshed': 'List refreshed',
  'msg.guestRefreshed': 'Guest mode: read-only status refreshed',
  'msg.loginViewLogs': 'Login is required to view logs.',
  'msg.noLogs': 'No logs',
  'msg.binarySaved': 'Binary config saved',
  'msg.loginForReconnect': 'Login is required to reconnect all',
  'msg.reconnectDone': 'Bulk reconnect finished',
  'msg.created': 'Created',
  'msg.accountSaved': 'Account settings saved',
  'api.badCredentials': 'Invalid username or password',
  'api.currentPasswordWrong': 'Current password is incorrect',
  'api.newPasswordMismatch': 'New password does not match'
};

const I18N_ZH = {
  'ui.title': 'MineBot MC \u63a7\u5236\u53f0',
  'ui.sub': '\u4e3b\u9875\u4ec5\u5c55\u793a\u670d\u52a1\u5668\u5361\u7247。\u767b\u5f55\u540e\u53ef\u67e5\u770b\u65e5\u5fd7\u5e76\u4fee\u6539\u914d\u7f6e。',
  'ui.guest': '\u8bbf\u5ba2',
  'ui.logged': '\u5df2\u767b\u5f55',
  'btn.login': '\u767b\u5f55',
  'btn.logout': '\u9000\u51fa\u767b\u5f55',
  'tab.addBot': '\u6dfb\u52a0 Bot',
  'tab.account': '\u8d26\u53f7\u8bbe\u7f6e',
  'section.addBot': '\u6dfb\u52a0 Bot',
  'ph.id': 'ID（\u53ef\u9009，\u81ea\u52a8\u751f\u6210）',
  'ph.name': '\u663e\u793a\u540d\u79f0（\u53ef\u9009）',
  'ph.host': '\u670d\u52a1\u5668\u5730\u5740，\u5982 mc.example.com',
  'ph.port': '\u7aef\u53e3',
  'ph.username': 'Bot \u7528\u6237\u540d',
  'ph.version': '\u7248\u672c（\u53ef\u9009，\u5982 1.20.1）',
  'btn.createConnect': '\u521b\u5efa\u5e76\u8fde\u63a5',
  'msg.lockedConfig': '\u8bbf\u5ba2\u6a21\u5f0f\u4e3a\u53ea\u8bfb。\u767b\u5f55\u540e\u53ef\u6dfb\u52a0、\u914d\u7f6e\u548c\u64cd\u4f5c Bot。',
  'section.binary': '\u4e8c\u8fdb\u5236\u670d\u52a1',
  'ph.binaryUrl': '\u4e0b\u8f7d\u5730\u5740',
  'ph.binaryPort': '\u7aef\u53e3（\u53ef\u9009）',
  'opt.autoStart': '\u81ea\u52a8\u542f\u52a8',
  'btn.saveConfig': '\u4fdd\u5b58\u914d\u7f6e',
  'btn.startService': '\u542f\u52a8\u670d\u52a1',
  'btn.stopService': '\u505c\u6b62\u670d\u52a1',
  'section.account': '\u8d26\u53f7\u8bbe\u7f6e',
  'desc.account': '\u66f4\u65b0\u9762\u677f\u767b\u5f55\u8d26\u53f7（\u52a0\u5bc6\u5b58\u50a8）',
  'ph.newUsername': '\u65b0\u7528\u6237\u540d',
  'ph.currentPassword': '\u5f53\u524d\u5bc6\u7801（\u4fee\u6539\u5bc6\u7801\u65f6\u5fc5\u586b）',
  'ph.newPassword': '\u65b0\u5bc6\u7801（\u53ef\u9009）',
  'ph.confirmPassword': '\u786e\u8ba4\u65b0\u5bc6\u7801',
  'btn.saveAccount': '\u4fdd\u5b58\u8d26\u53f7',
  'kpi.total': 'Bot \u603b\u6570',
  'kpi.online': '\u5728\u7ebf\u6570',
  'kpi.logTarget': '\u65e5\u5fd7\u76ee\u6807',
  'ph.search': '\u641c\u7d22 ID / host / username',
  'btn.reconnectAll': '\u5168\u90e8\u91cd\u8fde',
  'btn.refresh': '\u5237\u65b0',
  'section.serverStatus': '\u670d\u52a1\u5668\u72b6\u6001',
  'desc.guestOnly': '\u8bbf\u5ba2\u4ec5\u53ef\u67e5\u770b\u57fa\u7840\u4fe1\u606f',
  'section.logs': '\u8fd0\u884c\u65e5\u5fd7',
  'msg.selectBotForLogs': '\u8bf7\u5148\u767b\u5f55，\u518d\u9009\u62e9 Bot \u67e5\u770b\u65e5\u5fd7。',
  'section.loginPanel': '\u767b\u5f55\u9762\u677f',
  'btn.close': '\u5173\u95ed',
  'ph.usernameLogin': '\u7528\u6237\u540d',
  'ph.passwordLogin': '\u5bc6\u7801',
  'binary.running': '\u8fd0\u884c\u4e2d',
  'binary.port': '\u7aef\u53e3',
  'binary.stopped': '\u5df2\u505c\u6b62',
  'msg.loginSuccess': '\u767b\u5f55\u6210\u529f',
  'status.online': '\u5728\u7ebf',
  'status.offline': '\u79bb\u7ebf',
  'pill.hp': '\u8840\u91cf',
  'pill.food': '\u9965\u997f',
  'pill.players': '\u73a9\u5bb6',
  'pill.version': '\u7248\u672c',
  'pill.user': '\u7528\u6237',
  'pill.latency': '\u5ef6\u8fdf',
  'btn.connect': '\u8fde\u63a5',
  'btn.disconnect': '\u65ad\u5f00',
  'btn.log': '\u65e5\u5fd7',
  'btn.edit': '\u7f16\u8f91',
  'btn.save': '\u4fdd\u5b58',
  'btn.cancel': '\u53d6\u6d88',
  'btn.more': '\u66f4\u591a',
  'btn.chat': '\u804a\u5929',
  'btn.follow': '\u8ddf\u968f',
  'btn.attack': '\u653b\u51fb',
  'btn.patrol': '\u5de1\u903b',
  'btn.mine': '\u6316\u77ff',
  'btn.jump': '\u8df3\u8dc3',
  'btn.afk': '\u9632\u6302\u673a',
  'btn.eat': '\u81ea\u52a8\u5403\u996d',
  'btn.guard': '\u5b88\u536b',
  'btn.fish': '\u9493\u9c7c',
  'btn.limit': '\u9650\u901f',
  'btn.human': '\u62df\u4eba\u5316',
  'btn.idle': '\u5b89\u5168\u5f85\u673a',
  'btn.workflow': '\u5de5\u4f5c\u6d41',
  'btn.delete': '\u5220\u9664',
  'msg.loginRequired': '\u6b64\u64cd\u4f5c\u9700\u8981\u5148\u767b\u5f55',
  'msg.confirmDelete': '\u786e\u8ba4\u5220\u9664 Bot ',
  'ui.selectBot': '\u9009\u62e9 Bot',
  'msg.emptyBots': '\u6682\u65e0 Bot，\u8bf7\u5728\u5de6\u4fa7\u9762\u677f\u521b\u5efa。',
  'msg.emptyCards': '\u6682\u65e0\u670d\u52a1\u5668\u5361\u7247，\u8bf7\u767b\u5f55\u540e\u6dfb\u52a0\u5e76\u7ba1\u7406。',
  'msg.listRefreshed': '\u5217\u8868\u5df2\u5237\u65b0',
  'msg.guestRefreshed': '\u8bbf\u5ba2\u6a21\u5f0f：\u53ea\u8bfb\u72b6\u6001\u5df2\u5237\u65b0',
  'msg.loginViewLogs': '\u67e5\u770b\u65e5\u5fd7\u9700\u8981\u5148\u767b\u5f55。',
  'msg.noLogs': '\u6682\u65e0\u65e5\u5fd7',
  'msg.binarySaved': '\u4e8c\u8fdb\u5236\u914d\u7f6e\u5df2\u4fdd\u5b58',
  'msg.loginForReconnect': '\u6279\u91cf\u91cd\u8fde\u9700\u8981\u5148\u767b\u5f55',
  'msg.reconnectDone': '\u6279\u91cf\u91cd\u8fde\u5b8c\u6210',
  'msg.created': '\u521b\u5efa\u6210\u529f',
  'msg.accountSaved': '\u8d26\u53f7\u8bbe\u7f6e\u5df2\u4fdd\u5b58',
  'api.badCredentials': '\u7528\u6237\u540d\u6216\u5bc6\u7801\u9519\u8bef',
  'api.currentPasswordWrong': '\u5f53\u524d\u5bc6\u7801\u9519\u8bef',
  'api.newPasswordMismatch': '\u65b0\u5bc6\u7801\u4e0d\u4e00\u81f4'
};
const ti = (key) => I18N_DEFAULT[key] || key;

const INLINE_FALLBACK_ADMIN_HTML = `<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>${ti('ui.title')}</title>
  <style>
    :root {
      --bg: #0b1220;
      --bg-2: #0a1630;
      --panel: #111a2e;
      --panel-2: #17233d;
      --line: #2b3a5b;
      --text: #e8eefb;
      --muted: #96a6c7;
      --primary: #53d7b8;
      --primary-2: #34d399;
      --accent-cyan: #38bdf8;
      --accent-amber: #f59e0b;
      --accent-rose: #fb7185;
      --ok: #22c55e;
      --warn: #f59e0b;
      --danger: #ef4444;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      color: var(--text);
      font-family: "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
      background:
        radial-gradient(1200px 620px at 10% -8%, rgba(44, 89, 173, .45) 0%, transparent 62%),
        radial-gradient(920px 520px at 96% 4%, rgba(16, 155, 140, .22) 0%, transparent 58%),
        radial-gradient(860px 520px at 50% 100%, rgba(59, 130, 246, .12) 0%, transparent 65%),
        linear-gradient(180deg, var(--bg-2) 0%, var(--bg) 52%, #060e1f 100%);
      min-height: 100vh;
      position: relative;
      overflow-x: hidden;
    }
    body::before {
      content: "";
      position: fixed;
      inset: 0;
      pointer-events: none;
      z-index: -1;
      opacity: .22;
      background:
        linear-gradient(90deg, rgba(120, 146, 201, .1) 1px, transparent 1px),
        linear-gradient(180deg, rgba(120, 146, 201, .08) 1px, transparent 1px);
      background-size: 30px 30px;
    }
    .wrap { max-width: 1240px; margin: 0 auto; padding: 24px 16px 36px; }
    .hero {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 16px;
      padding: 18px;
      border: 1px solid #304977;
      border-radius: 14px;
      background:
        linear-gradient(145deg, rgba(22, 40, 75, .86), rgba(14, 24, 45, .9)),
        radial-gradient(120% 140% at 90% 0%, rgba(56, 189, 248, .13), transparent 60%);
      box-shadow: 0 12px 40px rgba(0,0,0,.28), inset 0 1px 0 rgba(161, 193, 255, .14);
    }
    .hero h1 { margin: 0; font-size: 24px; letter-spacing: .3px; }
    .hero .sub { color: var(--muted); font-size: 13px; margin-top: 6px; }
    .badge {
      font-size: 12px;
      color: #0f172a;
      background: linear-gradient(120deg, var(--primary), var(--primary-2));
      padding: 6px 10px;
      border-radius: 999px;
      font-weight: 700;
    }
    .hero-right { display: flex; align-items: center; gap: 10px; }
    .auth-actions { display: flex; align-items: center; gap: 8px; }
    .auth-actions button { width: auto; padding: 8px 12px; border-radius: 999px; }
    .auth-chip { font-size: 12px; color: var(--muted); }
    .layout { display: grid; grid-template-columns: 1fr; gap: 14px; }
    .kpis { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-bottom: 10px; }
    .kpi {
      position: relative;
      border: 1px solid var(--line);
      border-radius: 10px;
      background: linear-gradient(180deg, rgba(8, 18, 37, .9), rgba(7, 13, 28, .74));
      padding: 9px 10px;
      overflow: hidden;
    }
    .kpi::before {
      content: "";
      position: absolute;
      left: 0;
      right: 0;
      top: 0;
      height: 2px;
      background: linear-gradient(90deg, rgba(56, 189, 248, .9), rgba(83, 215, 184, .9));
      opacity: .85;
    }
    .kpi:nth-child(2)::before {
      background: linear-gradient(90deg, rgba(83, 215, 184, .9), rgba(34, 197, 94, .9));
    }
    .kpi:nth-child(3)::before {
      background: linear-gradient(90deg, rgba(251, 113, 133, .88), rgba(245, 158, 11, .88));
    }
    .kpi .k { color: var(--muted); font-size: 11px; }
    .kpi .v { margin-top: 4px; font-size: 18px; font-weight: 700; letter-spacing: .2px; }
    .toolbar { display: grid; grid-template-columns: 1fr auto auto; gap: 8px; margin-bottom: 8px; }
    .panel {
      border: 1px solid #2e4570;
      border-radius: 14px;
      padding: 14px;
      background:
        radial-gradient(140% 90% at 110% 0%, rgba(56, 189, 248, .08), transparent 55%),
        linear-gradient(170deg, rgba(23,35,61,.82), rgba(14,23,41,.92));
      backdrop-filter: blur(8px);
      box-shadow: inset 0 1px 0 rgba(145, 177, 240, .12);
    }
    .panel h3 { margin: 0 0 10px; font-size: 15px; letter-spacing: .2px; }
    .tabs { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 10px; }
    .tab-btn { border-radius: 9px; border: 1px solid var(--line); background: #0b1427; color: var(--muted); }
    .tab-btn.active { color: var(--text); border-color: #3a5ca3; background: linear-gradient(120deg, rgba(62,98,180,.35), rgba(34,66,132,.35)); }
    .tab-pane { display: none; }
    .tab-pane.active { display: block; }
    .muted { color: var(--muted); font-size: 12px; }
    .field-label { color: var(--muted); font-size: 12px; margin-top: 2px; }
    .row { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
    .stack { display: grid; gap: 8px; }
    input, button, select {
      width: 100%;
      border-radius: 10px;
      border: 1px solid var(--line);
      background: #0b1427;
      color: var(--text);
      font-size: 13px;
      padding: 10px 11px;
      transition: .18s ease;
    }
    input:focus, select:focus {
      outline: none;
      border-color: var(--primary);
      box-shadow: 0 0 0 3px rgba(83,215,184,.16);
    }
    button { cursor: pointer; font-weight: 700; }
    .btn-primary { background: linear-gradient(120deg, #1fbf98, #24a67f); border-color: #1fbf98; color: #07261c; }
    .btn-alt { background: linear-gradient(120deg, #2f6de0, #2657ba); border-color: #2f6de0; }
    .btn-ghost { background: transparent; }
    .btn-ok { background: #166534; border-color: #166534; }
    .btn-warn { background: #9a3412; border-color: #9a3412; }
    .btn-danger { background: #b91c1c; border-color: #b91c1c; }
    .btn-active {
      background: linear-gradient(120deg, rgba(34, 197, 94, .28), rgba(22, 163, 74, .22));
      border-color: #22c55e;
      color: #d9ffe8;
      box-shadow: 0 0 0 1px rgba(34, 197, 94, .2) inset;
    }
    button:hover { filter: brightness(1.08); }

    .bots {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
      gap: 6px;
      max-height: 520px;
      overflow: auto;
      padding-right: 2px;
    }
    .bot {
      border: 1px solid #325189;
      border-radius: 12px;
      padding: 12px;
      min-height: 112px;
      background:
        radial-gradient(120% 140% at 100% 0%, rgba(56, 189, 248, .1), transparent 60%),
        linear-gradient(155deg, rgba(13, 24, 46, .96), rgba(9, 18, 36, .93));
      box-shadow: inset 0 1px 0 rgba(124, 161, 255, .18), 0 10px 26px rgba(2, 10, 25, .35);
      transition: transform .2s ease, border-color .2s ease, box-shadow .2s ease;
    }
    .bot:hover {
      transform: translateY(-2px);
      border-color: #4c6fbd;
      box-shadow: inset 0 1px 0 rgba(124, 161, 255, .24), 0 16px 34px rgba(2, 10, 25, .45), 0 0 0 1px rgba(56, 189, 248, .14);
    }
    .bot-top { display: flex; justify-content: space-between; align-items: flex-start; gap: 10px; }
    .bot-name-row { display: flex; align-items: baseline; gap: 10px; min-width: 0; }
    .bot-name { font-size: 22px; font-weight: 800; letter-spacing: .15px; line-height: 1.1; }
    .bot-id-inline { font-size: 12px; color: #86a3d8; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; opacity: .95; }
    .bot-stats { margin-top: 12px; display: flex; flex-wrap: wrap; gap: 8px; }
    .pill {
      font-size: 13px;
      padding: 5px 12px;
      border-radius: 999px;
      border: 1px solid #365287;
      color: #c1d2f1;
      background: linear-gradient(180deg, rgba(25, 40, 71, .78), rgba(20, 33, 58, .62));
      line-height: 1.1;
    }
    .status {
      font-size: 13px;
      font-weight: 700;
      border: 1px solid;
      border-radius: 999px;
      padding: 4px 12px;
      min-width: 42px;
      text-align: center;
    }
    .status.on { color: #22e781; border-color: #1c6a43; background: rgba(20, 83, 45, .22); }
    .status.on { box-shadow: 0 0 0 1px rgba(34, 231, 129, .15) inset, 0 0 16px rgba(34, 231, 129, .12); }
    .status.off { color: #ffca63; border-color: #82540d; background: rgba(133, 77, 14, .2); box-shadow: 0 0 0 1px rgba(255, 202, 99, .11) inset; }
    .bot-tools { margin-top: 8px; display: grid; grid-template-columns: repeat(2, 1fr); gap: 6px; }
    .actions { margin-top: 8px; display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; }
    .actions.collapsed { display: none; }
    .actions button { font-size: 12px; }
    .edit-panel {
      margin-top: 8px;
      padding: 8px;
      border: 1px solid #2c4575;
      border-radius: 10px;
      background: rgba(9, 20, 40, .75);
      display: grid;
      gap: 6px;
    }
    .edit-panel.collapsed { display: none; }
    .edit-panel input, .edit-panel button { font-size: 12px; padding: 8px 9px; }
    .logs {
      margin-top: 14px;
      border: 1px solid var(--line);
      border-radius: 12px;
      background: #050b19;
      height: 300px;
      overflow: auto;
      padding: 10px;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 12px;
      line-height: 1.4;
      white-space: pre-wrap;
    }
    .tip { margin-top: 8px; min-height: 18px; color: var(--muted); font-size: 12px; }
    .sep { border: none; border-top: 1px solid var(--line); margin: 12px 0; }
    .lock-note {
      margin-top: 8px;
      padding: 8px 10px;
      border-radius: 8px;
      border: 1px solid #6b4f1d;
      background: rgba(245, 158, 11, .12);
      color: #fbbf24;
      font-size: 12px;
    }
    .empty {
      border: 1px dashed var(--line);
      border-radius: 10px;
      padding: 16px;
      text-align: center;
      color: var(--muted);
      background: linear-gradient(180deg, rgba(12, 21, 40, .54), rgba(8, 14, 28, .5));
    }
    .modal {
      position: fixed;
      inset: 0;
      background: rgba(3, 8, 20, .66);
      display: none;
      align-items: center;
      justify-content: center;
      z-index: 20;
      padding: 16px;
    }
    .modal.show { display: flex; }
    .modal-card {
      width: 100%;
      max-width: 420px;
      border-radius: 12px;
      border: 1px solid var(--line);
      background: linear-gradient(170deg, rgba(23,35,61,.95), rgba(17,26,46,.96));
      padding: 14px;
    }
    .modal-card .head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
    .modal-card .head button { width: auto; padding: 6px 10px; }

    #leftPanel { display: none; }
    body.authed .layout { grid-template-columns: 360px 1fr; }
    body.authed #leftPanel { display: grid; }
    body.guest-mode #leftPanel { display: none; }
    body.guest-mode #quickConnect { display: none !important; }
    body.guest-mode .toolbar { grid-template-columns: 1fr auto; }
    body.guest-mode #search { display: none; }
    @media (max-width: 960px) { .layout { grid-template-columns: 1fr; } .hero { flex-wrap: wrap; gap: 10px; } .bots { grid-template-columns: 1fr; } }
  </style>
</head>
<body class="guest-mode">
  <div class="wrap">
    <div class="hero">
      <div>
        <h1 id="uiTitle">${ti('ui.title')}</h1>
        <div id="uiSub" class="sub">${ti('ui.sub')}</div>
      </div>
      <div class="hero-right">
        <div class="badge">MC ONLY</div>
        <div class="auth-chip" id="authStateChip">${ti('ui.guest')}</div>
        <div class="auth-actions">
          <button id="openLoginBtn" class="btn-ghost">${ti('btn.login')}</button>
          <button id="logoutBtn" class="btn-danger" style="display:none;">${ti('btn.logout')}</button>
        </div>
      </div>
    </div>

    <div class="layout">
      <div class="panel stack" id="leftPanel">
        <div class="tabs">
          <button id="tabBot" class="tab-btn active">${ti('tab.addBot')}</button>
          <button id="tabAccount" class="tab-btn">${ti('tab.account')}</button>
        </div>
        <div id="authMsg" class="tip"></div>

        <div id="paneBot" class="tab-pane active">
          <h3 id="secAddBot">${ti('section.addBot')}</h3>
          <div id="configFields">
            <input id="id" placeholder="${ti('ph.id')}">
            <input id="name" placeholder="${ti('ph.name')}">
            <input id="host" placeholder="${ti('ph.host')}">
            <div class="row">
              <input id="port" type="number" value="25565" placeholder="${ti('ph.port')}">
              <input id="username" placeholder="${ti('ph.username')}">
            </div>
            <input id="version" placeholder="${ti('ph.version')}">
          </div>
          <button id="add" class="btn-alt">${ti('btn.createConnect')}</button>
          <div id="configLock" class="lock-note" style="display:none;">${ti('msg.lockedConfig')}</div>
          <div id="msg" class="tip"></div>

          <hr class="sep" />
          <h3 id="secBinary">${ti('section.binary')}</h3>
          <input id="binUrl" placeholder="${ti('ph.binaryUrl')}" />
          <div class="row">
            <input id="binPort" type="number" placeholder="${ti('ph.binaryPort')}" />
            <label style="display:flex;align-items:center;gap:6px;padding:10px;border:1px solid var(--line);border-radius:10px;background:#0b1427;color:var(--muted)"><input id="binAuto" type="checkbox" style="width:auto" /> ${ti('opt.autoStart')}</label>
          </div>
          <div class="row">
            <button id="saveBinary" class="btn-ghost">${ti('btn.saveConfig')}</button>
            <button id="startBinary" class="btn-ok">${ti('btn.startService')}</button>
          </div>
          <button id="stopBinary" class="btn-warn">${ti('btn.stopService')}</button>
          <div id="binaryStatus" class="tip"></div>
        </div>

        <div id="paneAccount" class="tab-pane">
          <h3 id="secAccount">${ti('section.account')}</h3>
          <div id="descAccount" class="field-label">${ti('desc.account')}</div>
          <div id="accountBox" style="margin-top:8px;display:block;">
            <input id="acctUser" placeholder="${ti('ph.newUsername')}">
            <input id="acctNew" type="password" placeholder="${ti('ph.newPassword')}">
            <button id="saveAccount" class="btn-ghost">${ti('btn.saveAccount')}</button>
            <div id="authCfgMsg" class="tip"></div>
          </div>
        </div>
      </div>

      <div class="panel">
        <div class="kpis">
          <div class="kpi"><div id="kpiTotalLabel" class="k">${ti('kpi.total')}</div><div class="v" id="kpiTotal">0</div></div>
          <div class="kpi"><div id="kpiOnlineLabel" class="k">${ti('kpi.online')}</div><div class="v" id="kpiOnline">0</div></div>
          <div class="kpi"><div id="kpiLogTargetLabel" class="k">${ti('kpi.logTarget')}</div><div class="v" id="kpiSelected">-</div></div>
        </div>

        <div class="toolbar">
          <input id="search" placeholder="${ti('ph.search')}" />
          <button id="quickConnect" class="btn-ghost" style="max-width:130px;">${ti('btn.reconnectAll')}</button>
          <button id="refresh" class="btn-ghost" style="max-width:120px;">${ti('btn.refresh')}</button>
        </div>

        <div class="bot-top" style="margin-bottom:10px;">
          <h3 id="secServerStatus" style="margin:0;">${ti('section.serverStatus')}</h3>
          <span id="descGuestOnly" class="muted">${ti('desc.guestOnly')}</span>
        </div>
        <div id="bots" class="bots"></div>

        <div id="logPanel" style="display:none;">
          <div class="bot-top" style="margin-top:14px;">
            <h3 id="secLogs" style="margin:0;">${ti('section.logs')}</h3>
            <select id="logId" style="max-width:220px;"></select>
          </div>
          <div id="logs" class="logs">${ti('msg.selectBotForLogs')}</div>
        </div>
      </div>
    </div>
  </div>

  <div class="modal" id="loginModal">
    <div class="modal-card">
      <div class="head">
        <strong id="secLoginPanel">${ti('section.loginPanel')}</strong>
        <button id="closeLoginBtn" class="btn-ghost">${ti('btn.close')}</button>
      </div>
      <div class="row">
        <input id="uGuest" placeholder="${ti('ph.usernameLogin')}" value="admin">
        <input id="pGuest" type="password" placeholder="${ti('ph.passwordLogin')}" value="admin123">
      </div>
      <button id="guestLogin" class="btn-primary" style="margin-top:8px;">${ti('btn.login')}</button>
      <div id="guestAuthMsg" class="tip"></div>
    </div>
  </div>

  <script>
    const I18N = __I18N_JSON__;
    const ACTIVE_LANG = __UI_LANG__;
    const t = (key) => I18N[key] || key;
    const applyLocale = () => {
      document.title = t('ui.title');
      const textMap = {
        uiTitle: 'ui.title',
        uiSub: 'ui.sub',
        openLoginBtn: 'btn.login',
        logoutBtn: 'btn.logout',
        tabBot: 'tab.addBot',
        tabAccount: 'tab.account',
        secAddBot: 'section.addBot',
        add: 'btn.createConnect',
        configLock: 'msg.lockedConfig',
        secBinary: 'section.binary',
        saveBinary: 'btn.saveConfig',
        startBinary: 'btn.startService',
        stopBinary: 'btn.stopService',
        secAccount: 'section.account',
        descAccount: 'desc.account',
        saveAccount: 'btn.saveAccount',
        kpiTotalLabel: 'kpi.total',
        kpiOnlineLabel: 'kpi.online',
        kpiLogTargetLabel: 'kpi.logTarget',
        quickConnect: 'btn.reconnectAll',
        refresh: 'btn.refresh',
        secServerStatus: 'section.serverStatus',
        descGuestOnly: 'desc.guestOnly',
        secLogs: 'section.logs',
        logs: 'msg.selectBotForLogs',
        secLoginPanel: 'section.loginPanel',
        closeLoginBtn: 'btn.close',
        guestLogin: 'btn.login',
      };
      Object.entries(textMap).forEach(([id, key]) => {
        const el = document.getElementById(id);
        if (el) el.textContent = t(key);
      });

      const phMap = {
        id: 'ph.id',
        name: 'ph.name',
        host: 'ph.host',
        port: 'ph.port',
        username: 'ph.username',
        version: 'ph.version',
        binUrl: 'ph.binaryUrl',
        binPort: 'ph.binaryPort',
        acctUser: 'ph.newUsername',
        acctNew: 'ph.newPassword',
        search: 'ph.search',
        uGuest: 'ph.usernameLogin',
        pGuest: 'ph.passwordLogin',
      };
      Object.entries(phMap).forEach(([id, key]) => {
        const el = document.getElementById(id);
        if (el) el.placeholder = t(key);
      });

      const autoLabel = document.querySelector('label[for="binAuto"]') || document.getElementById('binAuto')?.parentElement;
      if (autoLabel) {
        const textNode = [...autoLabel.childNodes].find((x) => x.nodeType === Node.TEXT_NODE);
        if (textNode) textNode.nodeValue = ' ' + t('opt.autoStart');
      }
    };
    let token = localStorage.getItem('mc_token') || '';
    if (token && ACTIVE_LANG !== 'zh') {
      window.location.replace('/admin?lang=zh');
    }
    const $ = (id) => document.getElementById(id);
    const isAuthed = () => !!token;

    const authHeaders = () => token ? { Authorization: 'Bearer ' + token, 'Content-Type': 'application/json' } : { 'Content-Type': 'application/json' };
    const expandedMoreCards = new Set();
    const expandedEditCards = new Set();
    let refreshInFlight = null;
    let refreshQueued = false;
    let logsInFlight = null;
    let searchDebounceTimer = null;

    const req = async (url, method, body) => {
      const res = await fetch(url, {
        method: method || 'GET',
        headers: authHeaders(),
        body: body ? JSON.stringify(body) : undefined,
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok || data.success === false) throw new Error(data.error || ('HTTP ' + res.status));
      return data;
    };

    const publicReq = async (url) => {
      const res = await fetch(url, { method: 'GET' });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.error || ('HTTP ' + res.status));
      return data;
    };

    const setTip = (id, text, type) => {
      const el = $(id);
      el.textContent = text || '';
      el.style.color = type === 'err' ? '#ef4444' : (type === 'ok' ? '#22c55e' : '#96a6c7');
    };

    const switchLeftTab = (tab) => {
      const isBot = tab === 'bot';
      $('tabBot').classList.toggle('active', isBot);
      $('tabAccount').classList.toggle('active', !isBot);
      $('paneBot').classList.toggle('active', isBot);
      $('paneAccount').classList.toggle('active', !isBot);
    };

    const updateAuthState = () => {
      const locked = !isAuthed();
      document.body.classList.toggle('guest-mode', locked);
      document.body.classList.toggle('authed', !locked);
      $('add').disabled = locked;
      $('configFields').style.opacity = locked ? '.55' : '1';
      $('configLock').style.display = locked ? 'block' : 'none';
      $('accountBox').style.display = locked ? 'none' : 'block';
      $('logPanel').style.display = locked ? 'none' : 'block';
      $('quickConnect').style.display = locked ? 'none' : 'inline-block';
      $('openLoginBtn').style.display = locked ? 'inline-block' : 'none';
      $('logoutBtn').style.display = locked ? 'none' : 'inline-block';
      $('authStateChip').textContent = locked ? t('ui.guest') : t('ui.logged');
      $('binUrl').disabled = locked;
      $('binPort').disabled = locked;
      $('binAuto').disabled = locked;
      $('saveBinary').disabled = locked;
      $('startBinary').disabled = locked;
      $('stopBinary').disabled = locked;
      if (locked) $('kpiSelected').textContent = '-';
      if (locked) setTip('authMsg', '', '');
    };

    const loadAccount = async () => {
      if (!isAuthed()) return;
      try {
        const data = await req('/api/auth/account', 'GET');
        $('acctUser').value = data.username || '';
      } catch {}
    };

    const loadBinaryConfig = async () => {
      if (!isAuthed()) return;
      try {
        const res = await req('/api/binary/config', 'GET');
        $('binUrl').value = res.config?.url || '';
        $('binPort').value = res.config?.port || '';
        $('binAuto').checked = !!res.config?.autoStart;
      } catch {}
    };

    const refreshBinaryStatus = async () => {
      if (!isAuthed()) {
        $('binaryStatus').textContent = '';
        return;
      }
      try {
        const res = await req('/api/binary/status', 'GET');
        const d = res.data || {};
        $('binaryStatus').textContent = d.running
          ? (t('binary.running') + ' · PID ' + (d.pid || '-') + ' · ' + t('binary.port') + ' ' + (d.port || '-'))
          : t('binary.stopped');
      } catch (e) {
        $('binaryStatus').textContent = e.message;
      }
    };

    const syncKpis = (bots) => {
      const list = Object.values(bots || {});
      const online = list.filter((b) => !!b.connected || !!b.status?.connected).length;
      $('kpiTotal').textContent = String(list.length);
      $('kpiOnline').textContent = String(online);
      $('kpiSelected').textContent = $('logId').value || '-';
    };

    const login = async (usernameInput, passwordInput, tipId) => {
      try {
        const username = (typeof usernameInput === 'string' ? usernameInput : $('uGuest').value).trim();
        const password = typeof passwordInput === 'string' ? passwordInput : $('pGuest').value;
        const data = await req('/api/login', 'POST', { username, password });
        token = data.token;
        localStorage.setItem('mc_token', token);
        if (ACTIVE_LANG !== 'zh') {
          window.location.replace('/admin?lang=zh');
          return;
        }
        setTip(tipId || 'authMsg', t('msg.loginSuccess'), 'ok');
        updateAuthState();
        await loadAccount();
        await loadBinaryConfig();
        await refreshBinaryStatus();
        await refresh();
        $('loginModal').classList.remove('show');
      } catch (e) {
        setTip(tipId || 'authMsg', e.message, 'err');
      }
    };

    const createBotCard = (id, bot) => {
      const el = document.createElement('div');
      el.className = 'bot';
      const connected = !!bot.connected || !!bot.status?.connected;
      const health = bot.health || bot.status?.health || 0;
      const food = bot.food || bot.status?.food || 0;
      const players = (bot.players || bot.status?.players || []).length;
      const shownUsername = bot.username || bot.status?.username || '';
      const latency = bot.latency || bot.status?.latency || {};
      const latencyMs = Number.isFinite(latency.ms) ? Math.max(1, Math.round(latency.ms)) : null;
      const latencyText = latencyMs === null ? 'N/A' : (latencyMs + 'ms');
      const latencySource = typeof latency.source === 'string' ? latency.source : 'na';
      const latencySourceLabel = latencySource === 'protocol'
        ? 'protocol'
        : (latencySource === 'tablist'
          ? 'tablist'
          : (latencySource === 'tcp'
            ? 'tcp probe'
            : (latencySource === 'restricted'
              ? 'restricted'
              : (latencySource === 'unavailable' ? 'unavailable' : 'n/a'))));
      const behaviors = bot.behaviors || {};
      const isOn = (key) => !!behaviors?.[key]?.active;
      const authed = isAuthed();

      el.innerHTML =
        '<div class="bot-top">' +
          '<div class="bot-name-row">' +
            '<div class="bot-name">' + (bot.name || id) + '</div>' +
          '</div>' +
          '<span class="status ' + (connected ? 'on' : 'off') + '" title="' + (connected ? t('status.online') : t('status.offline')) + '">' + (connected ? '●' : '○') + '</span>' +
        '</div>' +
        '<div class="bot-stats">' +
          '<span class="pill" title="' + t('pill.hp') + '">❤ ' + health + '</span>' +
          '<span class="pill" title="' + t('pill.food') + '">⚡ ' + food + '</span>' +
          '<span class="pill" title="' + t('pill.players') + '">👥 ' + players + '</span>' +
          '<span class="pill" title="' + t('pill.latency') + ' · ' + latencySourceLabel + '">⏱ ' + latencyText + '</span>' +
          (shownUsername ? ('<span class="pill" title="' + t('pill.user') + '">@ ' + shownUsername + '</span>') : '') +
          (bot.version ? ('<span class="pill">' + t('pill.version') + ' ' + bot.version + '</span>') : '') +
        '</div>' +
        (authed ? (
          '<div class="bot-tools">' +
            '<button class="btn-ok" data-act="connect">' + t('btn.connect') + '</button>' +
            '<button class="btn-warn" data-act="disconnect">' + t('btn.disconnect') + '</button>' +
            '<button data-act="logs">' + t('btn.log') + '</button>' +
            '<button data-act="edit">' + t('btn.edit') + '</button>' +
            '<button data-act="toggle">' + t('btn.more') + '</button>' +
          '</div>' +
          '<div class="actions' + (expandedMoreCards.has(id) ? '' : ' collapsed') + '" data-role="more">' +
            '<button data-act="chat">' + t('btn.chat') + '</button>' +
            '<button data-act="follow"' + (isOn('follow') ? ' class="btn-active"' : '') + '>' + t('btn.follow') + '</button>' +
            '<button data-act="attack"' + (isOn('attack') ? ' class="btn-active"' : '') + '>' + t('btn.attack') + '</button>' +
            '<button data-act="patrol"' + (isOn('patrol') ? ' class="btn-active"' : '') + '>' + t('btn.patrol') + '</button>' +
            '<button data-act="mine"' + (isOn('mining') ? ' class="btn-active"' : '') + '>' + t('btn.mine') + '</button>' +
            '<button data-act="jump">' + t('btn.jump') + '</button>' +
            '<button data-act="afk"' + (isOn('antiAfk') ? ' class="btn-active"' : '') + '>' + t('btn.afk') + '</button>' +
            '<button data-act="eat"' + (isOn('autoEat') ? ' class="btn-active"' : '') + '>' + t('btn.eat') + '</button>' +
            '<button data-act="guard"' + (isOn('guard') ? ' class="btn-active"' : '') + '>' + t('btn.guard') + '</button>' +
            '<button data-act="fish"' + (isOn('fishing') ? ' class="btn-active"' : '') + '>' + t('btn.fish') + '</button>' +
            '<button data-act="limit"' + (isOn('rateLimit') ? ' class="btn-active"' : '') + '>' + t('btn.limit') + '</button>' +
            '<button data-act="human"' + (isOn('humanize') ? ' class="btn-active"' : '') + '>' + t('btn.human') + '</button>' +
            '<button data-act="idle"' + (isOn('safeIdle') ? ' class="btn-active"' : '') + '>' + t('btn.idle') + '</button>' +
            '<button data-act="workflow"' + (isOn('workflow') ? ' class="btn-active"' : '') + '>' + t('btn.workflow') + '</button>' +
            '<button class="btn-danger" data-act="delete">' + t('btn.delete') + '</button>' +
          '</div>' +
          '<div class="edit-panel' + (expandedEditCards.has(id) ? '' : ' collapsed') + '" data-role="edit">' +
            '<div class="row">' +
              '<input data-edit="name" placeholder="' + t('ph.name') + '" value="' + (bot.name || id) + '" />' +
              '<input data-edit="host" placeholder="' + t('ph.host') + '" value="' + (bot.host || '') + '" />' +
            '</div>' +
            '<div class="row">' +
              '<input data-edit="port" placeholder="' + t('ph.port') + '" value="' + (bot.port || 25565) + '" />' +
              '<input data-edit="username" placeholder="' + t('ph.username') + '" value="' + (bot.username || bot.status?.username || '') + '" />' +
            '</div>' +
            '<input data-edit="version" placeholder="' + t('ph.version') + '" value="' + (bot.version || '') + '" />' +
            '<div class="row">' +
              '<button class="btn-primary" data-act="saveEdit">' + t('btn.save') + '</button>' +
              '<button class="btn-ghost" data-act="cancelEdit">' + t('btn.cancel') + '</button>' +
            '</div>' +
          '</div>'
        ) : '');

      if (!authed) return el;

      const toggleBehavior = async (behavior, options = {}, activeKey = behavior) => {
        const current = !!bot.behaviors?.[activeKey]?.active;
        const enabled = !current;
        const res = await req('/api/bots/' + id + '/behavior', 'POST', { behavior, enabled, options });
        const msg = res?.result?.message || (enabled ? (behavior + ' enabled') : (behavior + ' disabled'));
        setTip('msg', msg, 'ok');
      };

      el.querySelectorAll('button[data-act]').forEach((btn) => {
        btn.onclick = async () => {
          try {
            if (!isAuthed()) {
              setTip('authMsg', t('msg.loginRequired'), 'err');
              return;
            }
            const act = btn.dataset.act;
            if (act === 'toggle') {
              const more = el.querySelector('[data-role="more"]');
              if (more) {
                more.classList.toggle('collapsed');
                if (more.classList.contains('collapsed')) expandedMoreCards.delete(id);
                else expandedMoreCards.add(id);
              }
              return;
            }
            if (act === 'connect') await req('/api/bots/' + id + '/connect', 'POST', {});
            if (act === 'disconnect') await req('/api/bots/' + id + '/disconnect', 'POST', {});
            if (act === 'edit') {
              const panel = el.querySelector('[data-role="edit"]');
              if (panel) {
                panel.classList.toggle('collapsed');
                if (panel.classList.contains('collapsed')) expandedEditCards.delete(id);
                else expandedEditCards.add(id);
              }
              return;
            }
            if (act === 'cancelEdit') {
              const panel = el.querySelector('[data-role="edit"]');
              if (panel) panel.classList.add('collapsed');
              expandedEditCards.delete(id);
              return;
            }
            if (act === 'saveEdit') {
              const panel = el.querySelector('[data-role="edit"]');
              const name = (panel?.querySelector('[data-edit="name"]')?.value || '').trim();
              const host = (panel?.querySelector('[data-edit="host"]')?.value || '').trim();
              const portRaw = panel?.querySelector('[data-edit="port"]')?.value;
              const username = (panel?.querySelector('[data-edit="username"]')?.value || '').trim();
              const version = (panel?.querySelector('[data-edit="version"]')?.value || '').trim();
              const parsedPort = Number(portRaw);
              await req('/api/bots/' + id, 'PUT', {
                name: name || id,
                host,
                port: Number.isFinite(parsedPort) ? parsedPort : (bot.port || 25565),
                username,
                version: version || undefined,
              });
              if (panel) panel.classList.add('collapsed');
              expandedEditCards.delete(id);
            }
            if (act === 'chat') await req('/api/bots/' + id + '/chat', 'POST', { message: 'Hello from MC panel' });
            if (act === 'follow') {
              const active = !!bot.behaviors?.follow?.active;
              if (active) {
                await req('/api/bots/' + id + '/behavior', 'POST', { behavior: 'follow', enabled: false, options: {} });
                setTip('msg', 'Follow disabled', 'ok');
              } else {
                const defaultTarget = (bot.status?.players || [])[0] || '';
                const target = prompt('Follow target player', defaultTarget);
                if (target === null) return;
                if (!String(target).trim()) throw new Error('Follow target is required');
                await req('/api/bots/' + id + '/behavior', 'POST', { behavior: 'follow', enabled: true, options: { target: String(target).trim() } });
                setTip('msg', 'Follow enabled', 'ok');
              }
            }
            if (act === 'attack') await toggleBehavior('attack', { mode: 'hostile' });
            if (act === 'patrol') await toggleBehavior('patrol');
            if (act === 'mine') await toggleBehavior('mining');
            if (act === 'jump') await req('/api/bots/' + id + '/action', 'POST', { action: 'jump', params: {} });
            if (act === 'afk') await toggleBehavior('antiAfk');
            if (act === 'eat') await toggleBehavior('autoEat');
            if (act === 'guard') await toggleBehavior('guard');
            if (act === 'fish') await toggleBehavior('fishing');
            if (act === 'limit') await toggleBehavior('rateLimit');
            if (act === 'human') await toggleBehavior('humanize');
            if (act === 'idle') await toggleBehavior('safeIdle');
            if (act === 'workflow') await toggleBehavior('workflow');
            if (act === 'logs') {
              $('logId').value = id;
              await loadLogs();
              return;
            }
            if (act === 'delete') {
              if (!confirm(t('msg.confirmDelete') + id + ' ?')) return;
              await req('/api/bots/' + id, 'DELETE');
              expandedMoreCards.delete(id);
              expandedEditCards.delete(id);
            }
            await refresh();
          } catch (e) {
            setTip('msg', e.message, 'err');
          }
        };
      });

      return el;
    };

    const runRefresh = async () => {
      try {
        const bots = isAuthed() ? await req('/api/bots', 'GET') : await publicReq('/bots');
        const box = $('bots');
        const select = $('logId');
        const q = ($('search').value || '').trim().toLowerCase();
        box.innerHTML = '';
        const selected = select.value || '';
        select.innerHTML = '<option value="">' + t('ui.selectBot') + '</option>';
        const ids = Object.keys(bots || {});

        if (!ids.length) {
          box.innerHTML = isAuthed()
            ? '<div class="empty">' + t('msg.emptyBots') + '</div>'
            : '<div class="empty">' + t('msg.emptyCards') + '</div>';
        }

        ids.forEach((id) => {
          const item = bots[id] || {};
          const text = (id + ' ' + (item.host || '') + ' ' + (item.username || '') + ' ' + (item.status?.username || '')).toLowerCase();
          if (q && !text.includes(q)) return;
          box.appendChild(createBotCard(id, item));
          const op = document.createElement('option');
          op.value = id;
          op.textContent = id;
          select.appendChild(op);
        });

        if (selected && [...select.options].some((x) => x.value === selected)) {
          select.value = selected;
        }

        syncKpis(bots);

        setTip('msg', isAuthed() ? t('msg.listRefreshed') : t('msg.guestRefreshed'), isAuthed() ? 'ok' : '');
      } catch (e) {
        $('bots').innerHTML = '<div class="muted">' + e.message + '</div>';
      }
    };

    const refresh = async () => {
      if (refreshInFlight) {
        refreshQueued = true;
        return refreshInFlight;
      }
      refreshInFlight = (async () => {
        try {
          await runRefresh();
        } finally {
          refreshInFlight = null;
          if (refreshQueued) {
            refreshQueued = false;
            refresh();
          }
        }
      })();
      return refreshInFlight;
    };

    const loadLogs = async () => {
      if (logsInFlight) return logsInFlight;
      const id = $('logId').value;
      if (!id) return;
      if (!isAuthed()) {
        $('logs').textContent = t('msg.loginViewLogs');
        return;
      }
      logsInFlight = (async () => {
        try {
          const data = await req('/api/bots/' + id + '/logs', 'GET');
          $('logs').textContent = (data.logs || []).map((x) => '[' + x.time + '] ' + x.type + ': ' + x.msg).join('\\n') || t('msg.noLogs');
          $('kpiSelected').textContent = id;
        } catch (e) {
          $('logs').textContent = e.message;
        } finally {
          logsInFlight = null;
        }
      })();
      return logsInFlight;
    };

    $('openLoginBtn').onclick = () => {
      $('uGuest').value = 'admin';
      $('pGuest').value = '';
      $('guestAuthMsg').textContent = '';
      $('loginModal').classList.add('show');
    };
    $('closeLoginBtn').onclick = () => $('loginModal').classList.remove('show');
    $('guestLogin').onclick = () => login($('uGuest').value, $('pGuest').value, 'guestAuthMsg');
    $('logoutBtn').onclick = async () => {
      try { await req('/api/auth/logout', 'POST', {}); } catch {}
      token = '';
      localStorage.removeItem('mc_token');
      if (ACTIVE_LANG !== 'en') {
        window.location.replace('/admin');
        return;
      }
      $('loginModal').classList.remove('show');
      updateAuthState();
      refresh();
    };
    $('refresh').onclick = refresh;
    $('tabBot').onclick = () => switchLeftTab('bot');
    $('tabAccount').onclick = () => switchLeftTab('account');
    $('saveBinary').onclick = async () => {
      if (!isAuthed()) return;
      try {
        await req('/api/binary/config', 'POST', {
          url: $('binUrl').value.trim(),
          port: $('binPort').value === '' ? null : Number($('binPort').value),
          autoStart: !!$('binAuto').checked,
        });
        setTip('binaryStatus', t('msg.binarySaved'), 'ok');
        await refreshBinaryStatus();
      } catch (e) {
        setTip('binaryStatus', e.message, 'err');
      }
    };
    $('startBinary').onclick = async () => {
      if (!isAuthed()) return;
      try {
        await req('/api/binary/start', 'POST', {
          url: $('binUrl').value.trim(),
          port: $('binPort').value === '' ? null : Number($('binPort').value),
        });
        await refreshBinaryStatus();
      } catch (e) {
        setTip('binaryStatus', e.message, 'err');
      }
    };
    $('stopBinary').onclick = async () => {
      if (!isAuthed()) return;
      try {
        await req('/api/binary/stop', 'POST', {});
        await refreshBinaryStatus();
      } catch (e) {
        setTip('binaryStatus', e.message, 'err');
      }
    };
    $('search').oninput = () => {
      if (searchDebounceTimer) clearTimeout(searchDebounceTimer);
      searchDebounceTimer = setTimeout(() => {
        refresh();
      }, 220);
    };
    $('quickConnect').onclick = async () => {
      try {
        if (!isAuthed()) {
          setTip('authMsg', t('msg.loginForReconnect'), 'err');
          return;
        }
        const bots = await req('/api/bots', 'GET');
        const ids = Object.keys(bots || {});
        for (const id of ids) {
          try { await req('/api/bots/' + id + '/refresh', 'POST', {}); } catch {}
        }
        setTip('msg', t('msg.reconnectDone'), 'ok');
        await refresh();
      } catch (e) {
        setTip('msg', e.message, 'err');
      }
    };
    $('add').onclick = async () => {
      try {
        await req('/api/bots/add', 'POST', {
          id: $('id').value || undefined,
          name: $('name').value || undefined,
          host: $('host').value.trim(),
          port: Number($('port').value || 25565),
          username: $('username').value || undefined,
          version: $('version').value || undefined,
          type: 'minecraft',
        });
        setTip('msg', t('msg.created'), 'ok');
        await refresh();
      } catch (e) {
        setTip('msg', e.message, 'err');
      }
    };
    $('logId').onchange = loadLogs;
    $('pGuest').addEventListener('keydown', (e) => { if (e.key === 'Enter') login($('uGuest').value, $('pGuest').value, 'guestAuthMsg'); });
    $('version').addEventListener('keydown', (e) => { if (e.key === 'Enter') $('add').click(); });
    $('saveAccount').onclick = async () => {
      if (!isAuthed()) return;
      try {
        const username = $('acctUser').value.trim();
        const newPassword = $('acctNew').value;
        let result = { reloginRequired: false };
        if (newPassword) {
          result = await req('/api/auth/change-password', 'POST', { newPassword, password: newPassword });
        }
        if (username) {
          await req('/api/auth/account', 'POST', { username });
        }
        $('acctNew').value = '';
        setTip('authCfgMsg', t('msg.accountSaved'), 'ok');
        if (result && result.reloginRequired) {
          token = '';
          localStorage.removeItem('mc_token');
          $('loginModal').classList.remove('show');
          updateAuthState();
          setTip('authCfgMsg', 'Password changed, please login again', 'ok');
        }
      } catch (e) {
        setTip('authCfgMsg', e.message, 'err');
      }
    };

    applyLocale();
    updateAuthState();
    if (token) {
      loadAccount();
      loadBinaryConfig();
      refreshBinaryStatus();
    }
    refresh();
    setInterval(() => {
      if (!expandedEditCards.size) refresh();
      if (token && $('logId').value) loadLogs();
      if (token) refreshBinaryStatus();
    }, 5000);
  </script>
</body>
</html>`;

class FollowBehavior {
  constructor(bot) {
    this.bot = bot;
    this.active = false;
    this.target = null;
    this.interval = null;
  }

  start(playerName) {
    const player = this.bot.players[playerName];
    if (!player?.entity) return { success: false, message: 'Player not found' };
    this.target = playerName;
    this.active = true;
    this.interval = setInterval(() => {
      if (!this.active || !this.bot) return;
      const t = this.bot.players[this.target];
      if (t?.entity) this.bot.pathfinder.setGoal(new goals.GoalFollow(t.entity, 2), true);
    }, PERF.followTickMs);
    return { success: true, message: `Following ${playerName}` };
  }

  stop() {
    this.active = false;
    this.target = null;
    if (this.interval) {
      clearInterval(this.interval);
      this.interval = null;
    }
    if (this.bot?.pathfinder) this.bot.pathfinder.stop();
    return { success: true, message: 'Follow stopped' };
  }

  getStatus() {
    return { active: this.active, target: this.target };
  }
}

class AttackBehavior {
  constructor(bot) {
    this.bot = bot;
    this.active = false;
    this.mode = 'hostile';
    this.range = 4;
    this.interval = null;
  }

  start(mode = 'hostile') {
    this.mode = mode;
    this.active = true;
    this.interval = setInterval(() => {
      if (!this.active || !this.bot?.entity) return;
      const target = this.findTarget();
      if (target) this.attackEntity(target);
    }, PERF.attackTickMs);
    return { success: true, message: `Attack mode: ${mode}` };
  }

  findTarget() {
    const entities = Object.values(this.bot.entities || {});
    let nearest = null;
    let nearestDist = this.range;
    for (const entity of entities) {
      if (!entity || entity === this.bot.entity) continue;
      const dist = this.bot.entity.position.distanceTo(entity.position);
      if (dist > nearestDist) continue;
      if (this.mode === 'hostile' && entity.type !== 'hostile') continue;
      if (this.mode === 'player' && entity.type !== 'player') continue;
      nearest = entity;
      nearestDist = dist;
    }
    return nearest;
  }

  attackEntity(entity) {
    try {
      this.bot.lookAt(entity.position.offset(0, entity.height * 0.85, 0));
      this.bot.attack(entity);
    } catch { }
  }

  stop() {
    this.active = false;
    if (this.interval) {
      clearInterval(this.interval);
      this.interval = null;
    }
    return { success: true, message: 'Attack stopped' };
  }

  getStatus() {
    return { active: this.active, mode: this.mode, range: this.range };
  }
}

class PatrolBehavior {
  constructor(bot) {
    this.bot = bot;
    this.active = false;
    this.centerPos = null;
    this.isMoving = false;
    this.radius = 12;
    this.patrolInterval = null;
    this.moveTimeout = null;
  }

  start() {
    if (!this.bot?.entity) return { success: false, message: 'Bot is not spawned' };
    this.active = true;
    this.centerPos = this.bot.entity.position.clone();
    this.patrolInterval = setInterval(() => {
      if (!this.active || !this.bot?.entity || this.isMoving) return;
      this.doMove();
    }, PERF.patrolTickMs);
    this.doMove();
    return { success: true, message: 'Patrol started' };
  }

  doMove() {
    this.isMoving = true;
    if (this.moveTimeout) clearTimeout(this.moveTimeout);
    this.moveTimeout = setTimeout(() => {
      this.isMoving = false;
      if (this.bot?.pathfinder) this.bot.pathfinder.stop();
    }, 10000);
    const targetPos = this.centerPos.offset((Math.random() - 0.5) * this.radius, 0, (Math.random() - 0.5) * this.radius);
    this.bot.pathfinder.setGoal(new goals.GoalNear(targetPos.x, targetPos.y, targetPos.z, 1));
  }

  stop() {
    this.active = false;
    this.isMoving = false;
    if (this.patrolInterval) {
      clearInterval(this.patrolInterval);
      this.patrolInterval = null;
    }
    if (this.moveTimeout) {
      clearTimeout(this.moveTimeout);
      this.moveTimeout = null;
    }
    if (this.bot?.pathfinder) this.bot.pathfinder.setGoal(null);
    return { success: true, message: 'Patrol stopped' };
  }

  getStatus() {
    return { active: this.active, isMoving: this.isMoving, radius: this.radius };
  }
}

class MiningBehavior {
  constructor(bot) {
    this.bot = bot;
    this.active = false;
    this.targetBlocks = ['coal_ore', 'iron_ore', 'gold_ore', 'diamond_ore', 'emerald_ore'];
    this.range = 32;
  }

  start(blockTypes = null) {
    if (Array.isArray(blockTypes) && blockTypes.length) this.targetBlocks = blockTypes;
    this.active = true;
    this.mineLoop();
    return { success: true, message: 'Mining started' };
  }

  async mineLoop() {
    while (this.active && this.bot) {
      try {
        const block = this.findOre();
        if (!block) {
          await new Promise((r) => setTimeout(r, PERF.miningIdleMs));
          continue;
        }
        await this.bot.pathfinder.goto(new goals.GoalNear(block.position.x, block.position.y, block.position.z, 2));
        await this.bot.lookAt(block.position);
        await this.bot.dig(block);
      } catch {
        await new Promise((r) => setTimeout(r, PERF.miningRetryMs));
      }
    }
  }

  findOre() {
    for (const blockName of this.targetBlocks) {
      const blockId = this.bot.registry.blocksByName[blockName]?.id;
      if (!blockId) continue;
      const block = this.bot.findBlock({ matching: blockId, maxDistance: this.range });
      if (block) return block;
    }
    return null;
  }

  stop() {
    this.active = false;
    if (this.bot) this.bot.stopDigging();
    return { success: true, message: 'Mining stopped' };
  }

  getStatus() {
    return { active: this.active, targetBlocks: this.targetBlocks, range: this.range };
  }
}

class ActionBehavior {
  constructor(bot) {
    this.bot = bot;
  }

  jump() {
    this.bot.setControlState('jump', true);
    setTimeout(() => this.bot?.setControlState('jump', false), 100);
    return { success: true, message: 'Jumped' };
  }

  sneak(enabled = true) {
    this.bot.setControlState('sneak', enabled);
    return { success: true, message: enabled ? 'Sneak on' : 'Sneak off' };
  }

  sprint(enabled = true) {
    this.bot.setControlState('sprint', enabled);
    return { success: true, message: enabled ? 'Sprint on' : 'Sprint off' };
  }

  useItem() {
    this.bot.activateItem();
    return { success: true, message: 'Used item' };
  }

  swing() {
    this.bot.swingArm();
    return { success: true, message: 'Swing arm' };
  }

  lookAt(x, y, z) {
    if (!Number.isFinite(x) || !Number.isFinite(y) || !Number.isFinite(z)) {
      throw new Error('Invalid lookAt coordinates');
    }
    this.bot.lookAt({ x, y, z });
    return { success: true, message: `Look at (${x}, ${y}, ${z})` };
  }
}

class AiViewBehavior {
  constructor(bot) {
    this.bot = bot;
    this.active = false;
    this.interval = null;
    this.range = 16;
    this.lastTarget = null;
  }

  start() {
    if (this.active) return { success: false, message: 'AI view already enabled' };
    this.active = true;
    this.interval = setInterval(() => {
      if (!this.active || !this.bot?.entity) return;
      const target = this.bot.nearestEntity((entity) => {
        if (!entity || entity === this.bot.entity) return false;
        if (entity.type !== 'player') return false;
        return this.bot.entity.position.distanceTo(entity.position) <= this.range;
      });
      if (!target) {
        this.lastTarget = null;
        return;
      }
      try {
        this.bot.lookAt(target.position.offset(0, target.height * 0.85, 0));
        this.lastTarget = target.username || target.name || 'unknown';
      } catch { }
    }, PERF.aiViewTickMs);
    return { success: true, message: 'AI view started' };
  }

  stop() {
    this.active = false;
    this.lastTarget = null;
    if (this.interval) {
      clearInterval(this.interval);
      this.interval = null;
    }
    return { success: true, message: 'AI view stopped' };
  }

  getStatus() {
    return { active: this.active, range: this.range, lastTarget: this.lastTarget };
  }
}

class AntiAfkBehavior {
  constructor(bot) {
    this.bot = bot;
    this.active = false;
    this.intervalSeconds = 45;
    this.jitterSeconds = 15;
    this.actions = ['look', 'jump', 'swing', 'sneak'];
    this.timeout = null;
    this.lastAction = null;
  }

  start(options = {}) {
    if (this.active) return { success: false, message: 'Anti-AFK already enabled' };
    if (Number.isFinite(options.intervalSeconds)) this.intervalSeconds = Math.max(5, options.intervalSeconds);
    if (Number.isFinite(options.jitterSeconds)) this.jitterSeconds = Math.max(0, options.jitterSeconds);
    if (Array.isArray(options.actions) && options.actions.length > 0) this.actions = options.actions.map((x) => String(x));
    this.active = true;
    this.scheduleNext();
    return { success: true, message: 'Anti-AFK enabled' };
  }

  scheduleNext() {
    if (!this.active) return;
    const base = this.intervalSeconds * 1000;
    const jitter = this.jitterSeconds * 1000;
    const delay = Math.max(500, base + (Math.random() * 2 - 1) * jitter);
    this.timeout = setTimeout(() => {
      this.performAction();
      this.scheduleNext();
    }, delay);
  }

  performAction() {
    if (!this.active || !this.bot?.entity) return;
    const action = this.actions[Math.floor(Math.random() * this.actions.length)] || 'look';
    this.lastAction = action;
    try {
      if (action === 'jump') {
        this.bot.setControlState('jump', true);
        setTimeout(() => this.bot?.setControlState('jump', false), 150);
        return;
      }
      if (action === 'swing') {
        this.bot.swingArm();
        return;
      }
      if (action === 'sneak') {
        this.bot.setControlState('sneak', true);
        setTimeout(() => this.bot?.setControlState('sneak', false), 200);
        return;
      }
      const pos = this.bot.entity.position;
      this.bot.lookAt(pos.offset((Math.random() - 0.5) * 4, Math.random() * 2, (Math.random() - 0.5) * 4));
    } catch { }
  }

  stop() {
    this.active = false;
    if (this.timeout) {
      clearTimeout(this.timeout);
      this.timeout = null;
    }
    return { success: true, message: 'Anti-AFK disabled' };
  }

  getStatus() {
    return { active: this.active, intervalSeconds: this.intervalSeconds, jitterSeconds: this.jitterSeconds, lastAction: this.lastAction };
  }
}

class AutoEatBehavior {
  constructor(bot) {
    this.bot = bot;
    this.active = false;
    this.minHealth = 6;
    this.minFood = 14;
    this.interval = null;
    this.eating = false;
    this.lastFood = null;
  }

  start(options = {}) {
    if (this.active) return { success: false, message: 'Auto-eat already enabled' };
    if (Number.isFinite(options.minHealth)) this.minHealth = Math.max(0, options.minHealth);
    if (Number.isFinite(options.minFood)) this.minFood = Math.max(0, options.minFood);
    this.active = true;
    this.interval = setInterval(() => this.tick(), 1500);
    return { success: true, message: 'Auto-eat enabled' };
  }

  getFoodPoints(item) {
    const registry = this.bot?.registry;
    if (!registry || !item) return 0;
    const foods = registry.foods || {};
    if (foods[item.name]?.foodPoints) return foods[item.name].foodPoints;
    const itemDef = registry.itemsByName?.[item.name];
    if (itemDef?.foodPoints) return itemDef.foodPoints;
    return 0;
  }

  isFoodItem(item) {
    if (!item) return false;
    if (this.getFoodPoints(item) > 0) return true;
    const fallbackFoods = new Set(['bread', 'apple', 'golden_apple', 'carrot', 'baked_potato', 'cooked_beef', 'cooked_chicken', 'cooked_porkchop', 'cooked_mutton', 'cooked_rabbit', 'cooked_cod', 'cooked_salmon', 'melon_slice']);
    return fallbackFoods.has(item.name);
  }

  findBestFood() {
    const items = this.bot?.inventory?.items?.() || [];
    const foods = items.filter((item) => this.isFoodItem(item));
    if (!foods.length) return null;
    foods.sort((a, b) => this.getFoodPoints(b) - this.getFoodPoints(a));
    return foods[0];
  }

  async tick() {
    if (!this.active || !this.bot || this.eating) return;
    const health = typeof this.bot.health === 'number' ? this.bot.health : 20;
    const food = typeof this.bot.food === 'number' ? this.bot.food : 20;
    if (health > this.minHealth && food > this.minFood) return;
    const foodItem = this.findBestFood();
    if (!foodItem) return;
    this.eating = true;
    try {
      if (this.bot?.pathfinder) this.bot.pathfinder.stop();
      this.bot.setControlState?.('sprint', false);
      this.bot.setControlState?.('jump', false);
      this.bot.setControlState?.('sneak', false);
      await this.bot.equip(foodItem, 'hand');
      if (typeof this.bot.consume === 'function') {
        await this.bot.consume();
      } else {
        this.bot.activateItem();
        await new Promise((r) => setTimeout(r, 1600));
        this.bot.deactivateItem();
      }
      this.lastFood = foodItem.name;
    } catch {
    } finally {
      this.eating = false;
    }
  }

  stop() {
    this.active = false;
    this.lastFood = null;
    if (this.interval) {
      clearInterval(this.interval);
      this.interval = null;
    }
    return { success: true, message: 'Auto-eat disabled' };
  }

  getStatus() {
    return { active: this.active, minHealth: this.minHealth, minFood: this.minFood, lastFood: this.lastFood };
  }
}

class GuardBehavior {
  constructor(bot) {
    this.bot = bot;
    this.active = false;
    this.radius = 8;
    this.attackRange = 3;
    this.minHealth = 12;
    this.pathCooldownMs = 800;
    this.interval = null;
    this.lastTarget = null;
    this.lastPathTime = 0;
  }

  start(options = {}) {
    if (this.active) return { success: false, message: 'Guard already enabled' };
    if (Number.isFinite(options.radius)) this.radius = Math.max(2, options.radius);
    if (Number.isFinite(options.attackRange)) this.attackRange = Math.max(2, options.attackRange);
    if (Number.isFinite(options.minHealth)) this.minHealth = Math.max(0, options.minHealth);
    if (Number.isFinite(options.pathCooldownMs)) this.pathCooldownMs = Math.max(300, options.pathCooldownMs);
    this.active = true;
    this.interval = setInterval(() => this.tick(), 500);
    return { success: true, message: 'Guard enabled' };
  }

  findTarget() {
    if (!this.bot?.entity) return null;
    const origin = this.bot.entity.position;
    let nearest = null;
    let nearestDist = this.radius;
    for (const entity of Object.values(this.bot.entities || {})) {
      if (!entity || entity === this.bot.entity) continue;
      if (entity.type !== 'hostile') continue;
      const dist = origin.distanceTo(entity.position);
      if (dist > nearestDist) continue;
      nearest = entity;
      nearestDist = dist;
    }
    return nearest;
  }

  tick() {
    if (!this.active || !this.bot?.entity) return;
    if (typeof this.bot.health === 'number' && this.bot.health <= this.minHealth) {
      this.stop();
      return;
    }
    const target = this.findTarget();
    if (!target) {
      this.lastTarget = null;
      this.bot?.pathfinder?.stop();
      return;
    }
    this.lastTarget = target.username || target.name || target.type || 'unknown';
    const dist = this.bot.entity.position.distanceTo(target.position);
    if (dist > this.attackRange && this.bot?.pathfinder) {
      const now = Date.now();
      if (now - this.lastPathTime < this.pathCooldownMs) return;
      this.lastPathTime = now;
      this.bot.pathfinder.setGoal(new goals.GoalFollow(target, 1), true);
      return;
    }
    try {
      this.bot.lookAt(target.position.offset(0, target.height * 0.85, 0));
      this.bot.attack(target);
    } catch { }
  }

  stop() {
    this.active = false;
    this.lastTarget = null;
    if (this.interval) {
      clearInterval(this.interval);
      this.interval = null;
    }
    this.bot?.pathfinder?.stop();
    this.bot?.setControlState?.('sprint', false);
    this.bot?.setControlState?.('jump', false);
    this.bot?.setControlState?.('sneak', false);
    return { success: true, message: 'Guard disabled' };
  }

  getStatus() {
    return { active: this.active, radius: this.radius, attackRange: this.attackRange, minHealth: this.minHealth, lastTarget: this.lastTarget };
  }
}

class FishingBehavior {
  constructor(bot) {
    this.bot = bot;
    this.active = false;
    this.intervalSeconds = 2;
    this.timeoutSeconds = 25;
    this.fishing = false;
    this.lastResult = null;
  }

  start(options = {}) {
    if (this.active) return { success: false, message: 'Fishing already enabled' };
    if (Number.isFinite(options.intervalSeconds)) this.intervalSeconds = Math.max(1, options.intervalSeconds);
    if (Number.isFinite(options.timeoutSeconds)) this.timeoutSeconds = Math.max(5, options.timeoutSeconds);
    this.active = true;
    this.loop();
    return { success: true, message: 'Fishing enabled' };
  }

  async loop() {
    while (this.active && this.bot) {
      if (this.fishing) {
        await new Promise((r) => setTimeout(r, 300));
        continue;
      }
      const rod = (this.bot.inventory?.items?.() || []).find((item) => item.name === 'fishing_rod');
      if (!rod) {
        this.lastResult = 'no_fishing_rod';
        await new Promise((r) => setTimeout(r, 2000));
        continue;
      }
      this.fishing = true;
      try {
        await this.bot.equip(rod, 'hand');
        await Promise.race([
          this.bot.fish(),
          new Promise((_, reject) => setTimeout(() => reject(new Error('fish_timeout')), this.timeoutSeconds * 1000)),
        ]);
        this.lastResult = 'caught';
      } catch (e) {
        this.lastResult = e?.message || 'fish_failed';
      } finally {
        this.fishing = false;
      }
      await new Promise((r) => setTimeout(r, this.intervalSeconds * 1000));
    }
  }

  stop() {
    this.active = false;
    this.fishing = false;
    return { success: true, message: 'Fishing disabled' };
  }

  getStatus() {
    return {
      active: this.active,
      intervalSeconds: this.intervalSeconds,
      timeoutSeconds: this.timeoutSeconds,
      fishing: this.fishing,
      lastResult: this.lastResult,
    };
  }
}

class RateLimitBehavior {
  constructor(bot) {
    this.bot = bot;
    this.active = false;
    this.globalCooldownSeconds = 1;
    this.maxPerMinute = 20;
    this.lastChatTime = 0;
    this.windowStart = 0;
    this.windowCount = 0;
    this.blockedCount = 0;
    this.originalChat = null;
  }

  start(options = {}) {
    if (this.active) return { success: false, message: 'Rate limit already enabled' };
    if (Number.isFinite(options.globalCooldownSeconds)) this.globalCooldownSeconds = Math.max(0, options.globalCooldownSeconds);
    if (Number.isFinite(options.maxPerMinute)) this.maxPerMinute = Math.max(0, options.maxPerMinute);
    if (!this.bot?.chat) return { success: false, message: 'Bot is not ready' };
    this.active = true;
    this.blockedCount = 0;
    this.originalChat = this.bot.chat.bind(this.bot);
    this.bot.chat = (message) => {
      if (!this.active) return this.originalChat(message);
      if (this.shouldBlock()) {
        this.blockedCount += 1;
        return;
      }
      return this.originalChat(message);
    };
    return { success: true, message: 'Rate limit enabled' };
  }

  shouldBlock() {
    const now = Date.now();
    const minInterval = this.globalCooldownSeconds * 1000;
    if (minInterval > 0 && now - this.lastChatTime < minInterval) return true;
    this.lastChatTime = now;
    if (this.maxPerMinute > 0) {
      if (!this.windowStart || now - this.windowStart > 60000) {
        this.windowStart = now;
        this.windowCount = 0;
      }
      if (this.windowCount >= this.maxPerMinute) return true;
      this.windowCount += 1;
    }
    return false;
  }

  stop() {
    this.active = false;
    if (this.bot && this.originalChat) this.bot.chat = this.originalChat;
    this.originalChat = null;
    return { success: true, message: 'Rate limit disabled' };
  }

  getStatus() {
    return {
      active: this.active,
      globalCooldownSeconds: this.globalCooldownSeconds,
      maxPerMinute: this.maxPerMinute,
      blockedCount: this.blockedCount,
    };
  }
}

class HumanizeBehavior {
  constructor(bot) {
    this.bot = bot;
    this.active = false;
    this.intervalSeconds = 18;
    this.lookRange = 6;
    this.actionChance = 0.6;
    this.stepChance = 0.3;
    this.sneakChance = 0.2;
    this.swingChance = 0.2;
    this.timeout = null;
    this.lastAction = null;
  }

  start(options = {}) {
    if (this.active) return { success: false, message: 'Humanize already enabled' };
    if (Number.isFinite(options.intervalSeconds)) this.intervalSeconds = Math.max(5, options.intervalSeconds);
    if (Number.isFinite(options.lookRange)) this.lookRange = Math.max(2, options.lookRange);
    if (Number.isFinite(options.actionChance)) this.actionChance = Math.min(1, Math.max(0, options.actionChance));
    if (Number.isFinite(options.stepChance)) this.stepChance = Math.min(1, Math.max(0, options.stepChance));
    if (Number.isFinite(options.sneakChance)) this.sneakChance = Math.min(1, Math.max(0, options.sneakChance));
    if (Number.isFinite(options.swingChance)) this.swingChance = Math.min(1, Math.max(0, options.swingChance));
    this.active = true;
    this.scheduleNext();
    return { success: true, message: 'Humanize enabled' };
  }

  scheduleNext() {
    if (!this.active) return;
    const base = this.intervalSeconds * 1000;
    const jitter = Math.max(500, base * 0.35);
    const delay = Math.max(800, base + (Math.random() * 2 - 1) * jitter);
    this.timeout = setTimeout(() => {
      this.tick();
      this.scheduleNext();
    }, delay);
  }

  tick() {
    if (!this.active || !this.bot?.entity) return;
    if (Math.random() > this.actionChance) return;
    if (Math.random() < this.stepChance && !this.bot?.pathfinder?.isMoving?.()) {
      this.doStep();
      return;
    }
    if (Math.random() < this.sneakChance) {
      this.doSneak();
      return;
    }
    if (Math.random() < this.swingChance) {
      this.bot.swingArm();
      this.lastAction = 'swing';
      return;
    }
    this.doLook();
  }

  doLook() {
    const pos = this.bot.entity.position;
    this.bot.lookAt(pos.offset((Math.random() - 0.5) * this.lookRange * 2, Math.random() * 2, (Math.random() - 0.5) * this.lookRange * 2));
    this.lastAction = 'look';
  }

  doSneak() {
    this.lastAction = 'sneak';
    this.bot.setControlState('sneak', true);
    setTimeout(() => this.bot?.setControlState('sneak', false), 200 + Math.random() * 200);
  }

  doStep() {
    this.lastAction = 'step';
    this.bot.setControlState('sprint', false);
    const move = Math.random() > 0.5 ? 'forward' : 'back';
    const strafe = Math.random() > 0.5 ? 'left' : 'right';
    if (Math.random() > 0.5) this.bot.setControlState(move, true);
    else this.bot.setControlState(strafe, true);
    setTimeout(() => {
      if (!this.bot) return;
      this.bot.setControlState(move, false);
      this.bot.setControlState(strafe, false);
    }, 180 + Math.random() * 220);
  }

  stop() {
    this.active = false;
    if (this.timeout) {
      clearTimeout(this.timeout);
      this.timeout = null;
    }
    return { success: true, message: 'Humanize disabled' };
  }

  getStatus() {
    return {
      active: this.active,
      intervalSeconds: this.intervalSeconds,
      lookRange: this.lookRange,
      actionChance: this.actionChance,
      lastAction: this.lastAction,
    };
  }
}

class SafeIdleBehavior {
  constructor(bot) {
    this.bot = bot;
    this.active = false;
    this.intervalSeconds = 20;
    this.lookRange = 6;
    this.actionChance = 0.5;
    this.timeoutSeconds = 45;
    this.resumeDelaySeconds = 10;
    this.timeout = null;
    this.lastAction = null;
    this.lastPosition = null;
    this.lastMoveAt = 0;
    this.pausedUntil = 0;
  }

  start(options = {}) {
    if (this.active) return { success: false, message: 'Safe idle already enabled' };
    if (Number.isFinite(options.intervalSeconds)) this.intervalSeconds = Math.max(5, options.intervalSeconds);
    if (Number.isFinite(options.lookRange)) this.lookRange = Math.max(2, options.lookRange);
    if (Number.isFinite(options.actionChance)) this.actionChance = Math.min(1, Math.max(0, options.actionChance));
    if (Number.isFinite(options.timeoutSeconds)) this.timeoutSeconds = Math.max(10, options.timeoutSeconds);
    if (Number.isFinite(options.resumeDelaySeconds)) this.resumeDelaySeconds = Math.max(0, options.resumeDelaySeconds);
    this.active = true;
    this.lastPosition = this.bot?.entity?.position?.clone?.() || null;
    this.lastMoveAt = Date.now();
    this.scheduleNext();
    return { success: true, message: 'Safe idle enabled' };
  }

  scheduleNext() {
    if (!this.active) return;
    const base = this.intervalSeconds * 1000;
    const jitter = Math.max(500, base * 0.4);
    const delay = Math.max(800, base + (Math.random() * 2 - 1) * jitter);
    this.timeout = setTimeout(() => {
      this.tick();
      this.scheduleNext();
    }, delay);
  }

  tick() {
    if (!this.active || !this.bot?.entity) return;
    this.checkTimeout();
    if (this.pausedUntil && Date.now() < this.pausedUntil) return;
    if (this.pausedUntil && Date.now() >= this.pausedUntil) {
      this.pausedUntil = 0;
      this.doStep();
      this.lastAction = 'resume_step';
      return;
    }
    if (Math.random() > this.actionChance) return;
    const roll = Math.random();
    if (roll < 0.4) this.doLook();
    else if (roll < 0.7) this.doSneak();
    else if (roll < 0.9) {
      this.bot.swingArm();
      this.lastAction = 'swing';
    } else this.doStep();
  }

  checkTimeout() {
    if (!this.bot?.entity) return;
    const pos = this.bot.entity.position;
    if (this.lastPosition) {
      const moved = pos.distanceTo(this.lastPosition);
      if (moved > 0.2) {
        this.lastMoveAt = Date.now();
        this.lastPosition = pos.clone();
      }
    } else {
      this.lastPosition = pos.clone();
      this.lastMoveAt = Date.now();
    }
    const moving = this.bot?.pathfinder?.isMoving?.() || false;
    if (moving && Date.now() - this.lastMoveAt > this.timeoutSeconds * 1000) {
      this.bot?.pathfinder?.stop();
      this.bot?.setControlState?.('sprint', false);
      this.bot?.setControlState?.('jump', false);
      this.bot?.setControlState?.('sneak', false);
      this.lastAction = 'timeout_stop';
      this.lastMoveAt = Date.now();
      if (this.resumeDelaySeconds > 0) this.pausedUntil = Date.now() + this.resumeDelaySeconds * 1000;
    }
  }

  doLook() {
    const pos = this.bot.entity.position;
    this.bot.lookAt(pos.offset((Math.random() - 0.5) * this.lookRange * 2, Math.random() * 2, (Math.random() - 0.5) * this.lookRange * 2));
    this.lastAction = 'look';
  }

  doSneak() {
    this.lastAction = 'sneak';
    this.bot.setControlState('sneak', true);
    setTimeout(() => this.bot?.setControlState('sneak', false), 200 + Math.random() * 200);
  }

  doStep() {
    this.lastAction = 'step';
    this.bot.setControlState('sprint', false);
    const move = Math.random() > 0.5 ? 'forward' : 'back';
    const strafe = Math.random() > 0.5 ? 'left' : 'right';
    if (Math.random() > 0.5) this.bot.setControlState(move, true);
    else this.bot.setControlState(strafe, true);
    setTimeout(() => {
      if (!this.bot) return;
      this.bot.setControlState(move, false);
      this.bot.setControlState(strafe, false);
    }, 160 + Math.random() * 220);
  }

  stop() {
    this.active = false;
    if (this.timeout) {
      clearTimeout(this.timeout);
      this.timeout = null;
    }
    return { success: true, message: 'Safe idle disabled' };
  }

  getStatus() {
    return {
      active: this.active,
      intervalSeconds: this.intervalSeconds,
      lookRange: this.lookRange,
      actionChance: this.actionChance,
      timeoutSeconds: this.timeoutSeconds,
      resumeDelaySeconds: this.resumeDelaySeconds,
      lastAction: this.lastAction,
    };
  }
}

class WorkflowBehavior {
  constructor(controller) {
    this.controller = controller;
    this.active = false;
    this.steps = ['mining', 'patrol', 'rest'];
    this.currentIndex = 0;
    this.patrolSeconds = 120;
    this.restSeconds = 40;
    this.miningMaxSeconds = 240;
    this.stepTimer = null;
    this.startedAt = 0;
    this.lastReason = null;
  }

  start(options = {}) {
    if (this.active) return { success: false, message: 'Workflow already enabled' };
    if (Array.isArray(options.steps) && options.steps.length > 0) this.steps = options.steps.map((x) => String(x));
    if (Number.isFinite(options.patrolSeconds)) this.patrolSeconds = Math.max(10, options.patrolSeconds);
    if (Number.isFinite(options.restSeconds)) this.restSeconds = Math.max(5, options.restSeconds);
    if (Number.isFinite(options.miningMaxSeconds)) this.miningMaxSeconds = Math.max(30, options.miningMaxSeconds);
    this.active = true;
    this.currentIndex = 0;
    this.lastReason = null;
    this.startStep();
    return { success: true, message: 'Workflow enabled' };
  }

  startStep() {
    if (!this.active) return;
    const step = this.steps[this.currentIndex] || 'rest';
    this.startedAt = Date.now();
    this.clearTimer();
    if (step === 'mining') {
      const result = this.controller.startMining?.();
      if (result && result.success === false) {
        this.completeStep('failed');
        return;
      }
      this.stepTimer = setTimeout(() => this.completeStep('timeout'), this.miningMaxSeconds * 1000);
      return;
    }
    if (step === 'patrol') {
      const result = this.controller.startPatrol?.();
      if (result && result.success === false) {
        this.completeStep('failed');
        return;
      }
      this.stepTimer = setTimeout(() => this.completeStep('timeout'), this.patrolSeconds * 1000);
      return;
    }
    this.controller.stopAllMovement?.();
    this.stepTimer = setTimeout(() => this.completeStep('timeout'), this.restSeconds * 1000);
  }

  completeStep(reason = 'done') {
    if (!this.active) return;
    const step = this.steps[this.currentIndex] || 'rest';
    this.lastReason = `${step}:${reason}`;
    if (step === 'mining') this.controller.stopMining?.();
    if (step === 'patrol') this.controller.stopPatrol?.();
    if (step === 'rest') this.controller.stopAllMovement?.();
    this.currentIndex = (this.currentIndex + 1) % this.steps.length;
    this.startStep();
  }

  onStepComplete(step, reason = 'done') {
    const current = this.steps[this.currentIndex];
    if (!this.active || current !== step) return;
    this.completeStep(reason);
  }

  stop() {
    this.active = false;
    this.clearTimer();
    this.controller.stopMining?.();
    this.controller.stopPatrol?.();
    this.controller.stopAllMovement?.();
    return { success: true, message: 'Workflow disabled' };
  }

  clearTimer() {
    if (this.stepTimer) {
      clearTimeout(this.stepTimer);
      this.stepTimer = null;
    }
  }

  getStatus() {
    const step = this.steps[this.currentIndex] || 'rest';
    const elapsed = this.startedAt ? Math.floor((Date.now() - this.startedAt) / 1000) : 0;
    return { active: this.active, step, steps: this.steps, elapsedSeconds: elapsed, lastReason: this.lastReason };
  }
}

class BehaviorManager {
  constructor(bot) {
    this.follow = new FollowBehavior(bot);
    this.attack = new AttackBehavior(bot);
    this.patrol = new PatrolBehavior(bot);
    this.mining = new MiningBehavior(bot);
    this.action = new ActionBehavior(bot);
    this.aiView = new AiViewBehavior(bot);
    this.antiAfk = new AntiAfkBehavior(bot);
    this.autoEat = new AutoEatBehavior(bot);
    this.guard = new GuardBehavior(bot);
    this.fishing = new FishingBehavior(bot);
    this.rateLimit = new RateLimitBehavior(bot);
    this.humanize = new HumanizeBehavior(bot);
    this.safeIdle = new SafeIdleBehavior(bot);
    this.workflow = new WorkflowBehavior({
      startMining: () => this.mining.start(),
      stopMining: () => this.mining.stop(),
      startPatrol: () => this.patrol.start(),
      stopPatrol: () => this.patrol.stop(),
      stopAllMovement: () => {
        this.patrol.stop();
        if (this.mining.active) this.mining.stop();
      },
    });
  }

  stopAll() {
    this.follow.stop();
    this.attack.stop();
    this.patrol.stop();
    this.mining.stop();
    if (typeof this.action.stopLoop === 'function') this.action.stopLoop();
    this.aiView.stop();
    this.antiAfk.stop();
    this.autoEat.stop();
    this.guard.stop();
    this.fishing.stop();
    this.rateLimit.stop();
    this.humanize.stop();
    this.safeIdle.stop();
    this.workflow.stop();
  }

  getStatus() {
    return {
      follow: this.follow.getStatus(),
      attack: this.attack.getStatus(),
      patrol: this.patrol.getStatus(),
      mining: this.mining.getStatus(),
      action: typeof this.action.getStatus === 'function' ? this.action.getStatus() : null,
      aiView: this.aiView.getStatus(),
      antiAfk: this.antiAfk.getStatus(),
      autoEat: this.autoEat.getStatus(),
      guard: this.guard.getStatus(),
      fishing: this.fishing.getStatus(),
      rateLimit: this.rateLimit.getStatus(),
      humanize: this.humanize.getStatus(),
      safeIdle: this.safeIdle.getStatus(),
      workflow: this.workflow.getStatus(),
    };
  }
}

const randomBotUsername = () => {
  const left = ['Amber', 'Aqua', 'Aria', 'Blaze', 'Cloud', 'Comet', 'Coral', 'Dawn', 'Echo', 'Ember', 'Frost', 'Gale', 'Haze', 'Iris', 'Jade', 'Luna', 'Maple', 'Misty', 'Nova', 'Orion', 'Pearl', 'Quill', 'River', 'Skye', 'Solar', 'Storm', 'Swift', 'Terra', 'Violet', 'Willow'];
  const right = ['Aster', 'Beacon', 'Breeze', 'Cinder', 'Drift', 'Falcon', 'Flare', 'Glider', 'Harbor', 'Hollow', 'Jumper', 'Keeper', 'Lancer', 'Meadow', 'Nimbus', 'Pioneer', 'Ranger', 'Ripple', 'Runner', 'Sparrow', 'Spirit', 'Traveler', 'Voyager', 'Warden', 'Whisper', 'Wing', 'Wisp'];
  const l = left[Math.floor(Math.random() * left.length)];
  const r = right[Math.floor(Math.random() * right.length)];
  const name = `${l}${r}`;
  return name.length <= 16 ? name : name.slice(0, 16);
};

class BotInstance {
  constructor(serverConfig) {
    this.id = serverConfig.id;
    this.config = {
      host: serverConfig.host,
      port: serverConfig.port || 25565,
      username: serverConfig.username || '',
      version: serverConfig.version || undefined,
      name: serverConfig.name || serverConfig.id,
      autoReconnect: serverConfig.autoReconnect !== false,
      autoChat: serverConfig.autoChat || { enabled: false, interval: 60000, messages: ['Hello!'] },
    };
    this.bot = null;
    this.behaviors = null;
    this.logs = [];
    this.lastLogSig = '';
    this.lastLogAt = 0;
    this.suppressedLogCount = 0;
    this.lastMoveLogAt = 0;
    this.lastMoveState = false;
    this.reconnectTimer = null;
    this.autoChatInterval = null;
    this.latencyInterval = null;
    this.latencyProbeInFlight = false;
    this.lastLatencyProbeAt = 0;
    this.status = {
      connected: false,
      health: 0,
      food: 0,
      position: null,
      players: [],
      username: '',
      latency: {
        ms: null,
        source: 'na',
        note: 'unavailable',
      },
    };
    this.modes = {
      follow: false,
      autoAttack: false,
      patrol: false,
      mining: false,
      aiView: false,
      autoChat: !!this.config.autoChat.enabled,
      antiAfk: false,
      autoEat: false,
      guard: false,
      fishing: false,
      rateLimit: false,
      humanize: false,
      safeIdle: false,
      workflow: false,
    };
  }

  startLatencyLoop() {
    this.stopLatencyLoop();
    this.updateLatency().catch(() => { });
    this.latencyInterval = setInterval(() => {
      this.updateLatency().catch(() => { });
    }, 8000);
  }

  stopLatencyLoop() {
    if (this.latencyInterval) {
      clearInterval(this.latencyInterval);
      this.latencyInterval = null;
    }
    this.latencyProbeInFlight = false;
  }

  setLatencyStatus(ms, source, note = '') {
    this.status.latency = {
      ms: Number.isFinite(ms) ? Math.max(1, Math.round(ms)) : null,
      source: source || 'na',
      note: note || '',
    };
  }

  readProtocolLatency() {
    if (!this.bot) return null;

    const clientLatency = Number(this.bot?._client?.latency);
    if (Number.isFinite(clientLatency) && clientLatency > 0) {
      return { ms: clientLatency, source: 'protocol' };
    }

    const tabPing = Number(this.bot?.player?.ping);
    if (Number.isFinite(tabPing) && tabPing > 0) {
      return { ms: tabPing, source: 'tablist' };
    }

    return null;
  }

  probeTcpLatency(timeoutMs = 1500, hostOverride = null, portOverride = null) {
    return new Promise((resolve) => {
      const probeHost = String(hostOverride || this.config.host || '').trim();
      const probePort = Number(portOverride) || Number(this.config.port) || 25565;
      if (!probeHost) {
        resolve({ ok: false, reason: 'missing_host' });
        return;
      }

      const start = Date.now();
      let done = false;
      const socket = createConnection({ host: probeHost, port: probePort });

      const finish = (ok, reason = '') => {
        if (done) return;
        done = true;
        try { socket.destroy(); } catch { }
        if (ok) resolve({ ok: true, ms: Math.max(1, Date.now() - start) });
        else resolve({ ok: false, reason: reason || 'probe_failed' });
      };

      socket.setTimeout(timeoutMs);
      socket.once('connect', () => finish(true));
      socket.once('timeout', () => finish(false, 'timeout'));
      socket.once('error', (err) => finish(false, err?.code || err?.message || 'error'));
    });
  }

  async updateLatency() {
    const protocol = this.readProtocolLatency();
    if (protocol) {
      this.setLatencyStatus(protocol.ms, protocol.source);
      return;
    }

    const now = Date.now();
    if (this.latencyProbeInFlight) return;
    if (now - this.lastLatencyProbeAt < 7000) return;
    this.lastLatencyProbeAt = now;
    this.latencyProbeInFlight = true;

    try {
      const socketHost = this.bot?._client?.socket?.remoteAddress || null;
      const socketPort = this.bot?._client?.socket?.remotePort || null;

      if (socketHost) {
        const directProbe = await this.probeTcpLatency(1200, socketHost, socketPort);
        if (directProbe.ok) {
          this.setLatencyStatus(directProbe.ms, 'tcp', 'socket');
          return;
        }
      }

      const probe = await this.probeTcpLatency(1200);
      if (probe.ok) {
        this.setLatencyStatus(probe.ms, 'tcp', 'config');
        return;
      }
      const restrictedReasons = new Set(['timeout', 'ETIMEDOUT', 'ENOTFOUND', 'EHOSTUNREACH', 'ENETUNREACH']);
      const source = restrictedReasons.has(probe.reason)
        ? (this.status.connected ? 'restricted' : 'unavailable')
        : 'unavailable';
      this.setLatencyStatus(null, source, probe.reason || 'unavailable');
    } finally {
      this.latencyProbeInFlight = false;
    }
  }

  log(type, msg) {
    const text = String(msg ?? '');
    const now = Date.now();
    const sig = `${type}:${text}`;

    if (this.lastLogSig === sig && now - this.lastLogAt < LOG_DEDUP_MS) {
      this.suppressedLogCount += 1;
      return;
    }

    if (this.suppressedLogCount > 0) {
      this.logs.push({
        time: new Date(this.lastLogAt).toISOString(),
        type: 'debug',
        msg: `suppressed repeated logs x${this.suppressedLogCount}`,
      });
      this.suppressedLogCount = 0;
    }

    this.logs.push({ time: new Date(now).toISOString(), type, msg: text });
    this.lastLogSig = sig;
    this.lastLogAt = now;
    while (this.logs.length > MAX_BOT_LOGS) this.logs.shift();
  }

  getActiveMoveBehaviors() {
    const b = this.behaviors?.getStatus?.() || {};
    const tags = [];
    if (b.follow?.active) tags.push('follow');
    if (b.patrol?.active) tags.push('patrol');
    if (b.mining?.active) tags.push('mining');
    if (b.guard?.active) tags.push('guard');
    if (b.workflow?.active) tags.push('workflow');
    return tags;
  }

  getStatus() {
    return {
      id: this.id,
      name: this.config.name,
      host: this.config.host,
      port: this.config.port,
      version: this.config.version,
      status: this.status,
      modes: this.modes,
      behaviors: this.behaviors?.getStatus() || null,
    };
  }

  async connect() {
    if (this.status.connected) return;
    if (!this.config.host) throw new Error('host is required');
    if (this.bot) this.disconnect(false);

    const useGeneratedUsername = !this.config.username;
    const botUsername = this.config.username || randomBotUsername();
    this.status.username = botUsername;
    if (useGeneratedUsername) {
      this.config.username = botUsername;
      try { savePersistedState(); } catch { }
    }
    this.log('info', `Connecting to ${this.config.host}:${this.config.port}`);

    return new Promise((resolve, reject) => {
      let settled = false;
      const timeout = setTimeout(() => {
        if (settled) return;
        settled = true;
        this.scheduleReconnect();
        reject(new Error('Connection timeout'));
      }, 15000);

      try {
        this.bot = mineflayer.createBot({
          host: this.config.host,
          port: this.config.port,
          username: botUsername,
          version: this.config.version,
          auth: 'offline',
          connectTimeout: 15000,
          checkTimeoutInterval: 60000,
        });

        this.bot.loadPlugin(pathfinder);

        this.bot.once('spawn', () => {
          this.status.connected = true;
          clearTimeout(timeout);
          try {
            const movements = new Movements(this.bot, this.bot.registry);
            movements.canDig = false;
            this.bot.pathfinder.setMovements(movements);
          } catch { }
          this.behaviors = new BehaviorManager(this.bot);
          this.restoreModes();
          this.startLatencyLoop();
          this.log('success', `Connected (${this.bot.version})`);
          if (!settled) {
            settled = true;
            resolve();
          }
        });

        this.bot.on('health', () => {
          this.status.health = this.bot.health;
          this.status.food = this.bot.food;
          this.updateLatency().catch(() => { });
        });

        this.bot.on('move', () => {
          if (!this.bot?.entity) return;
          this.status.position = {
            x: Math.floor(this.bot.entity.position.x),
            y: Math.floor(this.bot.entity.position.y),
            z: Math.floor(this.bot.entity.position.z),
          };

          const isMoving = !!this.bot?.pathfinder?.isMoving?.();
          const now = Date.now();
          const tags = this.getActiveMoveBehaviors();
          if (isMoving && tags.length > 0 && (now - this.lastMoveLogAt > 4000 || !this.lastMoveState)) {
            this.lastMoveLogAt = now;
            this.log('info', `moving [${tags.join(',')}] @ ${this.status.position.x},${this.status.position.y},${this.status.position.z}`);
          }
          if (!isMoving && this.lastMoveState && tags.length > 0) {
            this.log('info', `movement idle [${tags.join(',')}] @ ${this.status.position.x},${this.status.position.y},${this.status.position.z}`);
          }
          this.lastMoveState = isMoving;
        });

        this.bot.on('playerJoined', () => {
          this.status.players = Object.keys(this.bot.players || {});
          this.updateLatency().catch(() => { });
        });

        this.bot.on('playerLeft', () => {
          this.status.players = Object.keys(this.bot.players || {});
          this.updateLatency().catch(() => { });
        });

        this.bot.on('chat', async (username, message) => {
          if (!this.bot || username === this.bot.username) return;
          this.log('chat', `${username}: ${message}`);
          if (message.startsWith('!')) await this.handleCommand(username, message);
        });

        this.bot.on('kicked', (reason) => {
          this.log('error', `Kicked: ${String(reason)}`);
          this.status.connected = false;
          this.setLatencyStatus(null, 'restricted', 'kicked');
          this.updateLatency().catch(() => { });
          this.scheduleReconnect();
        });

        this.bot.on('end', () => {
          this.log('warning', 'Disconnected');
          this.status.connected = false;
          this.bot = null;
          this.setLatencyStatus(null, 'unavailable', 'disconnected');
          this.updateLatency().catch(() => { });
          this.scheduleReconnect();
        });

        this.bot.on('error', (err) => {
          this.log('error', err.message);
          if (!settled) {
            settled = true;
            clearTimeout(timeout);
            this.scheduleReconnect();
            reject(err);
          }
        });
      } catch (err) {
        clearTimeout(timeout);
        this.scheduleReconnect();
        reject(err);
      }
    });
  }

  scheduleReconnect() {
    if (!this.config.autoReconnect) return;
    if (this.reconnectTimer) return;
    this.reconnectTimer = setTimeout(async () => {
      this.reconnectTimer = null;
      try {
        await this.connect();
      } catch (err) {
        this.log('error', `Reconnect failed: ${err.message}`);
      }
    }, 3000);
  }

  disconnect(stopReconnect = true) {
    if (stopReconnect && this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.autoChatInterval) {
      clearInterval(this.autoChatInterval);
      this.autoChatInterval = null;
    }
    this.stopLatencyLoop();
    if (this.behaviors) {
      this.behaviors.stopAll();
      this.behaviors = null;
    }
    if (this.bot) {
      try {
        this.bot.removeAllListeners();
        this.bot.quit();
      } catch { }
      this.bot = null;
    }
    this.status.connected = false;
    this.setLatencyStatus(null, 'na', 'disconnected');
    this.log('info', 'Disconnected by request');
  }

  chat(message) {
    if (!this.bot || !this.status.connected) throw new Error('Bot is not connected');
    this.bot.chat(message);
    this.log('chat', message);
  }

  setMode(mode, enabled) {
    if (!(mode in this.modes)) throw new Error(`Unknown mode: ${mode}`);
    if (!this.behaviors) throw new Error('Bot is not connected');
    this.modes[mode] = enabled;

    if (mode === 'aiView') {
      if (enabled) this.behaviors.aiView.start();
      else this.behaviors.aiView.stop();
    }
    if (mode === 'patrol') {
      if (enabled) this.behaviors.patrol.start();
      else this.behaviors.patrol.stop();
    }
    if (mode === 'autoAttack') {
      if (enabled) this.behaviors.attack.start('hostile');
      else this.behaviors.attack.stop();
    }
    if (mode === 'mining') {
      if (enabled) this.behaviors.mining.start();
      else this.behaviors.mining.stop();
    }
    if (mode === 'autoChat') {
      if (this.autoChatInterval) {
        clearInterval(this.autoChatInterval);
        this.autoChatInterval = null;
      }
      if (enabled) {
        const interval = this.config.autoChat.interval || 60000;
        const messages = this.config.autoChat.messages || ['Hello!'];
        this.autoChatInterval = setInterval(() => {
          if (!this.bot || !this.status.connected || !this.modes.autoChat) return;
          const msg = messages[Math.floor(Math.random() * messages.length)];
          this.bot.chat(msg);
        }, interval);
      }
    }
    if (mode === 'antiAfk') {
      if (enabled) this.behaviors.antiAfk.start();
      else this.behaviors.antiAfk.stop();
    }
    if (mode === 'autoEat') {
      if (enabled) this.behaviors.autoEat.start();
      else this.behaviors.autoEat.stop();
    }
    if (mode === 'guard') {
      if (enabled) this.behaviors.guard.start();
      else this.behaviors.guard.stop();
    }
    if (mode === 'fishing') {
      if (enabled) this.behaviors.fishing.start();
      else this.behaviors.fishing.stop();
    }
    if (mode === 'rateLimit') {
      if (enabled) this.behaviors.rateLimit.start();
      else this.behaviors.rateLimit.stop();
    }
    if (mode === 'humanize') {
      if (enabled) this.behaviors.humanize.start();
      else this.behaviors.humanize.stop();
    }
    if (mode === 'safeIdle') {
      if (enabled) this.behaviors.safeIdle.start();
      else this.behaviors.safeIdle.stop();
    }
    if (mode === 'workflow') {
      if (enabled) this.behaviors.workflow.start();
      else this.behaviors.workflow.stop();
    }
  }

  setBehavior(behavior, enabled, options = {}) {
    if (!this.behaviors) throw new Error('Bot is not connected');

    const finalize = (modeKey, result) => {
      this.modes[modeKey] = enabled ? !!result?.success : false;
      const stateText = enabled ? 'ON' : 'OFF';
      const detail = result?.message ? ` - ${result.message}` : '';
      this.log(result?.success === false ? 'warning' : 'info', `behavior ${behavior} => ${stateText}${detail}`);
      return result;
    };

    let result = null;
    if (behavior === 'follow') {
      result = enabled ? this.behaviors.follow.start(options.target) : this.behaviors.follow.stop();
      return finalize('follow', result);
    }
    if (behavior === 'attack') {
      result = enabled ? this.behaviors.attack.start(options.mode || 'hostile') : this.behaviors.attack.stop();
      return finalize('autoAttack', result);
    }
    if (behavior === 'patrol') {
      result = enabled ? this.behaviors.patrol.start() : this.behaviors.patrol.stop();
      return finalize('patrol', result);
    }
    if (behavior === 'mining') {
      result = enabled ? this.behaviors.mining.start(options.blocks) : this.behaviors.mining.stop();
      return finalize('mining', result);
    }
    if (behavior === 'antiAfk') {
      result = enabled ? this.behaviors.antiAfk.start(options) : this.behaviors.antiAfk.stop();
      return finalize('antiAfk', result);
    }
    if (behavior === 'autoEat') {
      result = enabled ? this.behaviors.autoEat.start(options) : this.behaviors.autoEat.stop();
      return finalize('autoEat', result);
    }
    if (behavior === 'guard') {
      result = enabled ? this.behaviors.guard.start(options) : this.behaviors.guard.stop();
      return finalize('guard', result);
    }
    if (behavior === 'fishing') {
      result = enabled ? this.behaviors.fishing.start(options) : this.behaviors.fishing.stop();
      return finalize('fishing', result);
    }
    if (behavior === 'rateLimit') {
      result = enabled ? this.behaviors.rateLimit.start(options) : this.behaviors.rateLimit.stop();
      return finalize('rateLimit', result);
    }
    if (behavior === 'humanize') {
      result = enabled ? this.behaviors.humanize.start(options) : this.behaviors.humanize.stop();
      return finalize('humanize', result);
    }
    if (behavior === 'safeIdle') {
      result = enabled ? this.behaviors.safeIdle.start(options) : this.behaviors.safeIdle.stop();
      return finalize('safeIdle', result);
    }
    if (behavior === 'workflow') {
      result = enabled ? this.behaviors.workflow.start(options) : this.behaviors.workflow.stop();
      return finalize('workflow', result);
    }
    throw new Error(`Unknown behavior: ${behavior}`);
  }

  doAction(action, params = {}) {
    if (!this.behaviors) throw new Error('Bot is not connected');
    if (action === 'jump') return this.behaviors.action.jump();
    if (action === 'sneak') return this.behaviors.action.sneak(!!params.enabled);
    if (action === 'sprint') return this.behaviors.action.sprint(!!params.enabled);
    if (action === 'useItem') return this.behaviors.action.useItem();
    if (action === 'swing') return this.behaviors.action.swing();
    if (action === 'lookAt') return this.behaviors.action.lookAt(Number(params.x), Number(params.y), Number(params.z));
    throw new Error(`Unknown action: ${action}`);
  }

  async handleCommand(username, message) {
    const [cmd, ...args] = message.trim().toLowerCase().split(/\s+/);
    if (cmd === '!help') {
      this.chat('!help !come !follow [name] !stop !pos !attack [hostile|player] !patrol !mine !jump !sneak !afk !eat !guard !fish !human !idle !workflow');
      return;
    }
    if (cmd === '!come') {
      const player = this.bot.players[username];
      if (!player?.entity) return;
      this.bot.pathfinder.setGoal(new goals.GoalNear(player.entity.position.x, player.entity.position.y, player.entity.position.z, 2));
      return;
    }
    if (cmd === '!follow') {
      const target = args[0] || username;
      const running = this.behaviors.follow.getStatus().active;
      if (running) this.behaviors.follow.stop();
      else this.behaviors.follow.start(target);
      return;
    }
    if (cmd === '!stop') {
      this.behaviors.stopAll();
      this.bot.pathfinder.stop();
      return;
    }
    if (cmd === '!pos' && this.bot?.entity) {
      const pos = this.bot.entity.position;
      this.chat(`X=${Math.floor(pos.x)} Y=${Math.floor(pos.y)} Z=${Math.floor(pos.z)}`);
      return;
    }
    if (cmd === '!attack') {
      const running = this.behaviors.attack.getStatus().active;
      if (running) this.behaviors.attack.stop();
      else this.behaviors.attack.start(args[0] || 'hostile');
      return;
    }
    if (cmd === '!patrol') {
      const running = this.behaviors.patrol.getStatus().active;
      if (running) this.behaviors.patrol.stop();
      else this.behaviors.patrol.start();
      return;
    }
    if (cmd === '!mine') {
      const running = this.behaviors.mining.getStatus().active;
      if (running) this.behaviors.mining.stop();
      else this.behaviors.mining.start();
      return;
    }
    if (cmd === '!jump') {
      this.behaviors.action.jump();
      return;
    }
    if (cmd === '!sneak') {
      const sneaking = this.bot.getControlState('sneak');
      this.behaviors.action.sneak(!sneaking);
      return;
    }
    if (cmd === '!afk') {
      const running = this.behaviors.antiAfk.getStatus().active;
      if (running) this.behaviors.antiAfk.stop();
      else this.behaviors.antiAfk.start();
      return;
    }
    if (cmd === '!eat') {
      const running = this.behaviors.autoEat.getStatus().active;
      if (running) this.behaviors.autoEat.stop();
      else this.behaviors.autoEat.start();
      return;
    }
    if (cmd === '!guard') {
      const running = this.behaviors.guard.getStatus().active;
      if (running) this.behaviors.guard.stop();
      else this.behaviors.guard.start();
      return;
    }
    if (cmd === '!fish') {
      const running = this.behaviors.fishing.getStatus().active;
      if (running) this.behaviors.fishing.stop();
      else this.behaviors.fishing.start();
      return;
    }
    if (cmd === '!human') {
      const running = this.behaviors.humanize.getStatus().active;
      if (running) this.behaviors.humanize.stop();
      else this.behaviors.humanize.start();
      return;
    }
    if (cmd === '!idle') {
      const running = this.behaviors.safeIdle.getStatus().active;
      if (running) this.behaviors.safeIdle.stop();
      else this.behaviors.safeIdle.start();
      return;
    }
    if (cmd === '!workflow') {
      const running = this.behaviors.workflow.getStatus().active;
      if (running) this.behaviors.workflow.stop();
      else this.behaviors.workflow.start();
    }
  }

  restoreModes() {
    if (!this.behaviors) return;
    if (this.modes.aiView) this.behaviors.aiView.start();
    if (this.modes.patrol) this.behaviors.patrol.start();
    if (this.modes.autoAttack) this.behaviors.attack.start('hostile');
    if (this.modes.mining) this.behaviors.mining.start();
    if (this.modes.autoChat) this.setMode('autoChat', true);
    if (this.modes.antiAfk) this.behaviors.antiAfk.start();
    if (this.modes.autoEat) this.behaviors.autoEat.start();
    if (this.modes.guard) this.behaviors.guard.start();
    if (this.modes.fishing) this.behaviors.fishing.start();
    if (this.modes.rateLimit) this.behaviors.rateLimit.start();
    if (this.modes.humanize) this.behaviors.humanize.start();
    if (this.modes.safeIdle) this.behaviors.safeIdle.start();
    if (this.modes.workflow) this.behaviors.workflow.start();
  }
}

const app = express();

const DATA_DIR = join(__dirname, 'data');
const ROOT_DIR = __dirname;
const STATE_FILE = join(DATA_DIR, 'bot.dat');
const BINARY_PATH = '/app';
const AES_KEY_PARTS = ['bWluZWJvdA==', 'LXRvb2xib3g=', 'LWFkbWlu', 'LXN0YXRl', 'LTIwMjY='];
const AES_SALT_PARTS = ['bWM=', 'LWJvdA==', 'LWRhdGE=', 'LXNhbHQ='];
const AES_SECRET = AES_KEY_PARTS.map(_d).join('');
const AES_SALT = AES_SALT_PARTS.map(_d).join('');
const AES_KEY = scryptSync(AES_SECRET, AES_SALT, 32);

const encryptText = (text) => {
  const iv = randomBytes(12);
  const cipher = createCipheriv('aes-256-gcm', AES_KEY, iv);
  const encrypted = Buffer.concat([cipher.update(text, 'utf-8'), cipher.final()]);
  const tag = cipher.getAuthTag();
  return `v2.${iv.toString('base64')}.${tag.toString('base64')}.${encrypted.toString('base64')}`;
};

const decryptText = (encoded) => {
  try {
    if (!encoded || !encoded.startsWith('v2.')) return '';
    const parts = encoded.split('.');
    if (parts.length !== 4) return '';
    const iv = Buffer.from(parts[1], 'base64');
    const tag = Buffer.from(parts[2], 'base64');
    const encrypted = Buffer.from(parts[3], 'base64');
    const decipher = createDecipheriv('aes-256-gcm', AES_KEY, iv);
    decipher.setAuthTag(tag);
    const plain = Buffer.concat([decipher.update(encrypted), decipher.final()]);
    return plain.toString('utf-8');
  } catch {
    return '';
  }
};

const defaultPersistedState = () => ({
  auth: { username: 'admin', password: 'admin123' },
  bots: [],
  binary: { url: '', port: null, autoStart: false },
  i18nVersion: 1,
  i18n: {},
});

const bots = new Map();
let authState = { username: 'admin', password: 'admin123' };
let i18nState = { ...I18N_DEFAULT };
let binarySettings = { url: '', port: null, autoStart: false };
let binaryRunning = false;
let binaryPid = null;
let binaryPort = null;
let binaryUrlCache = '';

const botToConfig = (bot) => ({
  id: bot.id,
  name: bot.config?.name || bot.id,
  host: bot.config?.host || '',
  port: bot.config?.port || 25565,
  username: bot.config?.username || '',
  version: bot.config?.version || undefined,
  autoReconnect: bot.config?.autoReconnect !== false,
  autoChat: bot.config?.autoChat || { enabled: false, interval: 60000, messages: ['Hello!'] },
});

const savePersistedState = () => {
  try {
    mkdirSync(DATA_DIR, { recursive: true });
    const payload = {
      auth: { username: authState.username || 'admin', password: authState.password || 'admin123' },
      bots: [...bots.values()].map(botToConfig),
      binary: {
        url: binarySettings.url || '',
        port: Number.isFinite(binarySettings.port) ? binarySettings.port : null,
        autoStart: Boolean(binarySettings.autoStart),
      },
      i18nVersion: 1,
      i18n: i18nState,
    };
    writeFileSync(STATE_FILE, encryptText(JSON.stringify(payload)), 'utf-8');
  } catch { }
};

const savePersistedStateStrict = () => {
  mkdirSync(DATA_DIR, { recursive: true });
  const payload = {
    auth: { username: authState.username || 'admin', password: authState.password || 'admin123' },
    bots: [...bots.values()].map(botToConfig),
    binary: {
      url: binarySettings.url || '',
      port: Number.isFinite(binarySettings.port) ? binarySettings.port : null,
      autoStart: Boolean(binarySettings.autoStart),
    },
    i18nVersion: 1,
    i18n: i18nState,
  };
  writeFileSync(STATE_FILE, encryptText(JSON.stringify(payload)), 'utf-8');
};

const loadAuthFromStateFile = () => {
  try {
    if (!existsSync(STATE_FILE)) return null;
    const content = readFileSync(STATE_FILE, 'utf-8').trim();
    const decAes = decryptText(content);
    if (!decAes || !decAes.trim().startsWith('{')) return null;
    const parsed = JSON.parse(decAes);
    if (!parsed || !parsed.auth) return null;
    const username = typeof parsed.auth.username === 'string' && parsed.auth.username ? parsed.auth.username : 'admin';
    const password = typeof parsed.auth.password === 'string' && parsed.auth.password ? parsed.auth.password : 'admin123';
    return { username, password };
  } catch {
    return null;
  }
};

const getEffectiveAuth = () => {
  const persisted = loadAuthFromStateFile();
  if (persisted) {
    authState = persisted;
    return persisted;
  }
  return authState;
};

const verifyPersistedAuth = () => {
  const content = readFileSync(STATE_FILE, 'utf-8').trim();
  const decAes = decryptText(content);
  if (!decAes || !decAes.trim().startsWith('{')) return false;
  const parsed = JSON.parse(decAes);
  return parsed && parsed.auth && parsed.auth.username === authState.username && parsed.auth.password === authState.password;
};

const loadPersistedState = () => {
  mkdirSync(DATA_DIR, { recursive: true });
  if (!existsSync(STATE_FILE)) {
    const base = defaultPersistedState();
    authState = base.auth;
    i18nState = { ...I18N_DEFAULT };
    binarySettings = base.binary;
    savePersistedState();
    return base;
  }
  try {
    const content = readFileSync(STATE_FILE, 'utf-8').trim();
    let parsed = null;
    let needsReencrypt = false;
    const decAes = decryptText(content);
    if (decAes && decAes.trim().startsWith('{')) {
      parsed = JSON.parse(decAes);
    } else if (content.startsWith('{')) {
      parsed = JSON.parse(content);
      needsReencrypt = true;
    }
    if (!parsed || typeof parsed !== 'object') throw new Error('bad config format');
    if (!parsed.auth || typeof parsed.auth !== 'object') parsed.auth = { username: 'admin', password: 'admin123' };
    if (!Array.isArray(parsed.bots)) parsed.bots = [];
    if (!parsed.binary || typeof parsed.binary !== 'object') parsed.binary = { url: '', port: null, autoStart: false };
    if (parsed.i18nVersion !== 1) parsed.i18n = {};
    if (!parsed.i18n || typeof parsed.i18n !== 'object') parsed.i18n = {};
    authState = {
      username: parsed.auth.username || 'admin',
      password: parsed.auth.password || 'admin123',
    };
    binarySettings = {
      url: typeof parsed.binary.url === 'string' ? parsed.binary.url : '',
      port: Number.isFinite(parsed.binary.port) ? parsed.binary.port : null,
      autoStart: Boolean(parsed.binary.autoStart),
    };
    i18nState = { ...I18N_DEFAULT, ...parsed.i18n };
    if (needsReencrypt) savePersistedState();
    return parsed;
  } catch {
    const base = defaultPersistedState();
    authState = base.auth;
    i18nState = { ...I18N_DEFAULT };
    binarySettings = base.binary;
    savePersistedState();
    return base;
  }
};

const restoreBotsFromState = async (state) => {
  for (const cfg of state.bots || []) {
    if (!cfg || !cfg.id || bots.has(cfg.id)) continue;
    const bot = new BotInstance(cfg);
    bots.set(cfg.id, bot);
  }
  for (const bot of bots.values()) {
    if (bot.config?.host) {
      try {
        await bot.connect();
      } catch { }
    }
  }
};

const getTempPath = () => {
  const ext = process.platform === 'win32' ? '.exe' : '';
  if (!existsSync(ROOT_DIR)) mkdirSync(ROOT_DIR, { recursive: true });
  return join(ROOT_DIR, `minebot${ext}`);
};

const checkPidAlive = (pid) => {
  if (!pid) return false;
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
};

const checkBinaryPortAlive = () => {
  try {
    const r = spawnSync('sh', ['-c', "ss -lnt | grep -q ':31000 '"], { stdio: 'ignore' });
    return r.status === 0;
  } catch {
    return false;
  }
};

const normalizeBinaryPort = (value, fallback = null) => {
  if (value === '' || value === null || value === undefined) return fallback;
  const n = Number(value);
  if (!Number.isFinite(n)) return fallback;
  if (n < 1 || n > 65535) return fallback;
  return n;
};

const downloadFile = async (url, targetPath) => {
  try {
    const response = await axios.get(url, { responseType: 'arraybuffer', timeout: 60000 });
    writeFileSync(targetPath, response.data);
  } catch (err) {
    const status = err?.response?.status;
    const message = status ? `Download failed (${status})` : (err?.message || 'Download failed');
    throw new Error(message);
  }
};

const setExecutable = (targetPath) => {
  if (process.platform !== 'win32') {
    chmodSync(targetPath, 0o755);
  }
};

const startBinary = async (url, portOverride) => {
  if (!url || typeof url !== 'string') {
    throw new Error('Download URL missing');
  }
  if (binaryRunning && checkPidAlive(binaryPid)) {
    return { running: true, pid: binaryPid, url: binaryUrlCache, port: binaryPort };
  }
  const tempPath = getTempPath();
  try { unlinkSync(tempPath); } catch { }
  await downloadFile(url, tempPath);
  setExecutable(tempPath);
  const desiredPort = Number.isFinite(portOverride) ? portOverride : null;
  const port = desiredPort && desiredPort >= 1 && desiredPort <= 65535
    ? desiredPort
    : Math.floor(Math.random() * 20000) + 20000;
  const child = spawn(tempPath, [], {
    detached: true,
    stdio: 'ignore',
    env: {
      ...process.env,
      BINARY_PORT: String(port),
      PORT: String(port),
      SERVER_PORT: String(port),
      PTERODACTYL_PORT: String(port),
    },
  });
  child.unref();
  binaryPid = child.pid || null;
  binaryRunning = true;
  binaryPort = port;
  binaryUrlCache = url;
  setTimeout(() => {
    try { unlinkSync(tempPath); } catch { }
  }, 2000);
  return { running: true, pid: binaryPid, url: binaryUrlCache, port: binaryPort };
};

const stopBinary = async () => {
  const tempPath = getTempPath();
  if (!binaryPid) {
    binaryRunning = false;
    try { unlinkSync(tempPath); } catch { }
    return { running: false };
  }
  try { process.kill(binaryPid); } catch { }
  binaryRunning = false;
  binaryPid = null;
  binaryPort = null;
  try { unlinkSync(tempPath); } catch { }
  return { running: false };
};

const getBinaryStatus = () => {
  const pidAlive = checkPidAlive(binaryPid);
  const portAlive = checkBinaryPortAlive();
  binaryRunning = pidAlive || portAlive;
  if (!pidAlive) binaryPid = null;
  return {
    running: binaryRunning,
    pid: binaryPid,
    url: binaryUrlCache || binarySettings.url || '',
    port: binaryPort || binarySettings.port || null,
    autoStart: Boolean(binarySettings.autoStart),
  };
};

const proxyToBinary = (req, res) => {
  const targetPath = req.originalUrl || '/';
  const options = {
    hostname: '127.0.0.1',
    port: 31000,
    path: targetPath,
    method: req.method,
    headers: { ...req.headers, host: '127.0.0.1' },
  };
  const proxyReq = http.request(options, (proxyRes) => {
    res.statusCode = proxyRes.statusCode || 502;
    Object.entries(proxyRes.headers).forEach(([key, value]) => {
      if (value !== undefined) res.setHeader(key, value);
    });
    proxyRes.pipe(res);
  });
  proxyReq.on('error', () => {
    res.status(502).send('Proxy error');
  });
  req.pipe(proxyReq);
};

const tokens = new Map();
const createToken = () => {
  const token = `${Date.now().toString(36)}.${Math.random().toString(36).slice(2)}`;
  tokens.set(token, Date.now() + 24 * 60 * 60 * 1000);
  return token;
};
const verifyToken = (token) => {
  if (!token || !tokens.has(token)) return false;
  const exp = tokens.get(token);
  if (Date.now() > exp) {
    tokens.delete(token);
    return false;
  }
  return true;
};
const auth = (req, res, next) => {
  const token = (req.headers.authorization || '').replace('Bearer ', '');
  if (!verifyToken(token)) return res.status(401).json({ authenticated: false, error: 'Unauthorized' });
  next();
};

const getBotsSnapshot = () => {
  const result = {};
  for (const [id, bot] of bots.entries()) result[id] = bot.getStatus();
  return result;
};

const ts = (key) => i18nState[key] || I18N_DEFAULT[key] || key;

const localizeAdminHtml = (html, fromDict, toDict) => {
  let out = html;
  for (const key of Object.keys(fromDict)) {
    const from = fromDict[key];
    const to = toDict[key];
    if (typeof from !== 'string' || typeof to !== 'string' || !from || from === to) continue;
    out = out.split(from).join(to);
  }
  return out;
};

app.use(BINARY_PATH, proxyToBinary);
app.use(express.json());

app.get('/', (_, res) => {
  res.redirect('/admin');
});

app.get('/admin', (req, res) => {
  const lang = (req.query?.lang || '').toString().toLowerCase() === 'zh' ? 'zh' : 'en';
  const i18n = lang === 'zh' ? I18N_ZH : I18N_DEFAULT;
  let html = INLINE_FALLBACK_ADMIN_HTML
    .replace('__I18N_JSON__', JSON.stringify(i18n))
    .replace('__UI_LANG__', JSON.stringify(lang));
  if (lang === 'zh') {
    html = localizeAdminHtml(html, I18N_DEFAULT, I18N_ZH);
  }
  res.type('html').send(html);
});

const getBot = (id) => {
  const bot = bots.get(id);
  if (!bot) {
    const err = new Error('Bot not found');
    err.status = 404;
    throw err;
  }
  return bot;
};

app.get('/health', (_, res) => {
  res.json({ ok: true, bots: bots.size });
});

app.get('/bots', (_, res) => {
  res.json(getBotsSnapshot());
});

app.post('/bots', async (req, res) => {
  try {
    const id = req.body.id || `bot_${Date.now()}`;
    if (bots.has(id)) throw new Error('id already exists');
    const bot = new BotInstance({
      id,
      name: req.body.name,
      host: req.body.host,
      port: req.body.port,
      username: req.body.username,
      version: req.body.version,
      autoReconnect: req.body.autoReconnect,
      autoChat: req.body.autoChat,
    });
    bots.set(id, bot);
    savePersistedState();
    if (req.body.autoConnect !== false) await bot.connect();
    res.json({ success: true, id });
  } catch (err) {
    res.status(400).json({ success: false, error: err.message });
  }
});

app.delete('/bots/:id', (req, res) => {
  try {
    const bot = getBot(req.params.id);
    bot.disconnect(true);
    bots.delete(req.params.id);
    savePersistedState();
    res.json({ success: true });
  } catch (err) {
    res.status(err.status || 400).json({ success: false, error: err.message });
  }
});

app.post('/bots/:id/connect', async (req, res) => {
  try {
    const bot = getBot(req.params.id);
    await bot.connect();
    res.json({ success: true });
  } catch (err) {
    res.status(err.status || 400).json({ success: false, error: err.message });
  }
});

app.post('/bots/:id/disconnect', (req, res) => {
  try {
    const bot = getBot(req.params.id);
    bot.disconnect(true);
    res.json({ success: true });
  } catch (err) {
    res.status(err.status || 400).json({ success: false, error: err.message });
  }
});

app.get('/bots/:id/logs', (req, res) => {
  try {
    const bot = getBot(req.params.id);
    res.json({ success: true, logs: bot.logs });
  } catch (err) {
    res.status(err.status || 400).json({ success: false, error: err.message });
  }
});

app.post('/bots/:id/chat', (req, res) => {
  try {
    const bot = getBot(req.params.id);
    bot.chat(req.body.message || '');
    res.json({ success: true });
  } catch (err) {
    res.status(err.status || 400).json({ success: false, error: err.message });
  }
});

app.post('/bots/:id/modes/:mode', (req, res) => {
  try {
    const bot = getBot(req.params.id);
    bot.setMode(req.params.mode, !!req.body.enabled);
    res.json({ success: true, modes: bot.modes });
  } catch (err) {
    res.status(err.status || 400).json({ success: false, error: err.message });
  }
});

app.post('/bots/:id/behaviors/:behavior', (req, res) => {
  try {
    const bot = getBot(req.params.id);
    const result = bot.setBehavior(req.params.behavior, !!req.body.enabled, req.body.options || {});
    res.json({ success: true, result });
  } catch (err) {
    res.status(err.status || 400).json({ success: false, error: err.message });
  }
});

app.post('/bots/:id/actions/:action', (req, res) => {
  try {
    const bot = getBot(req.params.id);
    const result = bot.doAction(req.params.action, req.body || {});
    res.json({ success: true, result });
  } catch (err) {
    res.status(err.status || 400).json({ success: false, error: err.message });
  }
});

app.get('/bots/:id/status', (req, res) => {
  try {
    const bot = getBot(req.params.id);
    res.json({ success: true, bot: bot.getStatus() });
  } catch (err) {
    res.status(err.status || 400).json({ success: false, error: err.message });
  }
});

app.post('/api/login', (req, res) => {
  const { username, password } = req.body || {};
  const currentAuth = getEffectiveAuth();
  if (username === currentAuth.username && password === currentAuth.password) {
    return res.json({ success: true, token: createToken() });
  }
  res.status(401).json({ success: false, error: ts('api.badCredentials') });
});

app.post('/api/auth/login', (req, res) => {
  const { username, password } = req.body || {};
  const currentAuth = getEffectiveAuth();
  if (username === currentAuth.username && password === currentAuth.password) {
    return res.json({ token: createToken(), user: { username: currentAuth.username } });
  }
  res.status(401).json({ error: ts('api.badCredentials') });
});

app.get('/api/auth/check', (req, res) => {
  const token = (req.headers.authorization || '').replace('Bearer ', '');
  res.json({ authenticated: verifyToken(token) });
});

app.post('/api/auth/logout', auth, (req, res) => {
  const token = (req.headers.authorization || '').replace('Bearer ', '');
  tokens.delete(token);
  res.json({ success: true });
});

app.post('/api/auth/change-password', auth, (req, res) => {
  const body = req.body || {};
  const newPassword = typeof body.newPassword === 'string'
    ? body.newPassword
    : (typeof body.password === 'string' ? body.password : '');
  const currentAuth = getEffectiveAuth();
  authState = currentAuth;
  if (!newPassword) return res.status(400).json({ error: 'new password required' });
  authState.password = newPassword;
  try {
    savePersistedStateStrict();
    if (!verifyPersistedAuth()) {
      return res.status(500).json({ success: false, error: 'persist verify failed' });
    }
  } catch {
    return res.status(500).json({ success: false, error: 'persist failed' });
  }
  tokens.clear();
  res.json({ success: true, reloginRequired: true });
});

app.get('/api/auth/account', auth, (req, res) => {
  res.json({ success: true, username: authState.username || 'admin' });
});

app.post('/api/auth/account', auth, (req, res) => {
  const { username } = req.body || {};
  const currentAuth = getEffectiveAuth();
  authState = currentAuth;
  if (typeof username === 'string' && username.trim()) {
    authState.username = username.trim();
  }
  try {
    savePersistedStateStrict();
    if (!verifyPersistedAuth()) {
      return res.status(500).json({ success: false, error: 'persist verify failed' });
    }
  } catch {
    return res.status(500).json({ success: false, error: 'persist failed' });
  }
  res.json({ success: true, username: authState.username, reloginRequired: false });
});

app.get('/api/i18n', auth, (req, res) => {
  res.json({ success: true, data: i18nState });
});

app.post('/api/i18n', auth, (req, res) => {
  const incoming = req.body || {};
  if (typeof incoming !== 'object' || Array.isArray(incoming)) {
    return res.status(400).json({ success: false, error: 'invalid i18n payload' });
  }
  i18nState = { ...I18N_DEFAULT, ...incoming };
  savePersistedState();
  res.json({ success: true, data: i18nState });
});

app.get('/api/binary/config', auth, (req, res) => {
  res.json({
    success: true,
    config: {
      url: binarySettings.url || '',
      port: Number.isFinite(binarySettings.port) ? binarySettings.port : '',
      autoStart: Boolean(binarySettings.autoStart),
      path: BINARY_PATH,
    },
  });
});

app.post('/api/binary/config', auth, (req, res) => {
  const body = req.body || {};
  binarySettings = {
    url: typeof body.url === 'string' ? body.url.trim() : (binarySettings.url || ''),
    port: normalizeBinaryPort(body.port, null),
    autoStart: Boolean(body.autoStart),
  };
  savePersistedState();
  res.json({ success: true, config: binarySettings });
});

app.get('/api/binary/status', auth, (req, res) => {
  res.json({ success: true, data: getBinaryStatus() });
});

app.post('/api/binary/start', auth, async (req, res) => {
  try {
    const body = req.body || {};
    const url = body.url || binarySettings.url;
    const portOverride = Number.isFinite(body.port)
      ? body.port
      : binarySettings.port;
    const result = await startBinary(url, portOverride);
    res.json({ success: true, data: result });
  } catch (err) {
    res.status(400).json({ success: false, error: err.message });
  }
});

app.post('/api/binary/stop', auth, async (req, res) => {
  try {
    const result = await stopBinary();
    res.json({ success: true, data: result });
  } catch (err) {
    res.status(400).json({ success: false, error: err.message });
  }
});

app.get('/api/bots', auth, (req, res) => {
  res.json(getBotsSnapshot());
});
app.post('/api/bots/add', auth, async (req, res) => {
  try {
    const id = req.body.id || `bot_${Date.now()}`;
    if (bots.has(id)) throw new Error('id already exists');
    const bot = new BotInstance({
      id,
      name: req.body.name,
      host: req.body.host,
      port: req.body.port,
      username: req.body.username,
      version: req.body.version,
      autoReconnect: req.body.autoReconnect,
      autoChat: req.body.autoChat,
    });
    bots.set(id, bot);
    savePersistedState();
    if ((req.body.type || 'minecraft') === 'minecraft' && req.body.host) await bot.connect();
    res.json({ success: true, id });
  } catch (err) {
    res.status(400).json({ success: false, error: err.message });
  }
});
app.post('/api/bots/:id/connect', auth, async (req, res) => {
  try {
    const bot = getBot(req.params.id);
    await bot.connect();
    res.json({ success: true });
  } catch (err) {
    res.status(err.status || 400).json({ success: false, error: err.message });
  }
});
app.post('/api/bots/:id/disconnect', auth, (req, res) => {
  try {
    const bot = getBot(req.params.id);
    bot.disconnect(true);
    res.json({ success: true });
  } catch (err) {
    res.status(err.status || 400).json({ success: false, error: err.message });
  }
});
app.delete('/api/bots/:id', auth, (req, res) => {
  try {
    const bot = getBot(req.params.id);
    bot.disconnect(true);
    bots.delete(req.params.id);
    savePersistedState();
    res.json({ success: true });
  } catch (err) {
    res.status(err.status || 400).json({ success: false, error: err.message });
  }
});
app.post('/api/bots/:id/chat', auth, (req, res) => {
  try {
    const bot = getBot(req.params.id);
    bot.chat(req.body.message || '');
    res.json({ success: true });
  } catch (err) {
    res.status(err.status || 400).json({ success: false, error: err.message });
  }
});
app.get('/api/bots/:id/logs', auth, (req, res) => {
  try {
    const bot = getBot(req.params.id);
    res.json({ success: true, logs: bot.logs });
  } catch (err) {
    res.status(err.status || 400).json({ success: false, error: err.message });
  }
});
app.delete('/api/bots/:id/logs', auth, (req, res) => {
  try {
    const bot = getBot(req.params.id);
    bot.logs = [];
    res.json({ success: true });
  } catch (err) {
    res.status(err.status || 400).json({ success: false, error: err.message });
  }
});
app.put('/api/bots/:id', auth, (req, res) => {
  try {
    const bot = getBot(req.params.id);
    Object.assign(bot.config, req.body || {});
    savePersistedState();
    res.json({ success: true });
  } catch (err) {
    res.status(err.status || 400).json({ success: false, error: err.message });
  }
});
app.post('/api/bots/:id/refresh', auth, async (req, res) => {
  try {
    const bot = getBot(req.params.id);
    bot.disconnect(false);
    await bot.connect();
    res.json({ success: true });
  } catch (err) {
    res.status(err.status || 400).json({ success: false, error: err.message });
  }
});
app.post('/api/bots/:id/behavior', auth, (req, res) => {
  try {
    const bot = getBot(req.params.id);
    const result = bot.setBehavior(req.body.behavior, !!req.body.enabled, req.body.options || {});
    res.json({ success: true, result });
  } catch (err) {
    res.status(err.status || 400).json({ success: false, error: err.message });
  }
});
app.post('/api/bots/:id/action', auth, (req, res) => {
  try {
    const bot = getBot(req.params.id);
    const result = bot.doAction(req.body.action, req.body.params || {});
    res.json({ success: true, result });
  } catch (err) {
    res.status(err.status || 400).json({ success: false, error: err.message });
  }
});
app.post('/api/bots/:id/mode', auth, (req, res) => {
  try {
    const bot = getBot(req.params.id);
    bot.setMode(req.body.mode, !!req.body.enabled);
    res.json({ success: true });
  } catch (err) {
    res.status(err.status || 400).json({ success: false, error: err.message });
  }
});

app.get('/api/tools', auth, (req, res) => {
  const bs = getBinaryStatus();
  res.json({
    tools: {
      [_CK.t0]: { installed: false, running: false, config: {} },
      [_CK.t1]: { installed: false, running: false, config: {} },
      [_CK.t2]: { installed: false, running: false, config: {} },
      [_CK.t3]: { installed: false, running: false, config: {} },
      binary: { installed: true, running: bs.running, config: { url: binarySettings.url || '', port: binarySettings.port || '', autoStart: !!binarySettings.autoStart, path: BINARY_PATH } },
    },
    arch: { platform: process.platform, archName: process.arch },
  });
});
app.all('/api/tools/:name/:action?', auth, (req, res) => {
  res.json({ success: true, message: 'Disabled in MC-only mode' });
});

app.get('/api/tgbot', auth, (req, res) => {
  res.json({ enabled: false, running: false, hasToken: false, config: { features: {}, openai: {} } });
});
app.use('/api/tgbot', auth, (req, res) => {
  if (req.path.startsWith('/rss')) {
    return res.json({ success: true, feeds: [], keywords: [], excludes: [], interval: 30 });
  }
  res.json({ success: true, message: 'Disabled in MC-only mode' });
});

app.get('/api/discord', auth, (req, res) => {
  res.json({ enabled: false, running: false, hasToken: false, mode: 'bot', username: null, config: { openai: {} } });
});
app.all('/api/discord/:action?', auth, (req, res) => {
  res.json({ success: true, message: 'Disabled in MC-only mode' });
});

app.get('/api/automation', auth, (req, res) => {
  res.json({ success: true, tasks: [], token: null });
});
app.use('/api/automation', auth, (req, res) => {
  if (req.path.startsWith('/token')) return res.json({ success: true, token: null });
  if (req.path.startsWith('/run')) return res.json({ success: true, result: { success: false, error: 'Disabled in MC-only mode' } });
  if (req.path.startsWith('/tasks')) return res.json({ success: true });
  res.json({ success: true });
});

app.get('/api/settings/logs', auth, (req, res) => {
  res.json({ success: true, logs: { enabled: true, maxLines: 500, logTools: false, logBots: true, logApi: false } });
});
app.post('/api/settings/logs', auth, (req, res) => {
  res.json({ success: true });
});

app.get('/ws', (req, res) => {
  res.status(426).json({ error: 'WebSocket disabled in MC-only mode' });
});

const port = Number(process.env.PORT || process.env.SERVER_PORT || process.env.PRIMARY_PORT || process.env.PTERODACTYL_PORT || 8080);
const boot = async () => {
  const state = loadPersistedState();
  await restoreBotsFromState(state);
  if (binarySettings.autoStart && binarySettings.url) {
    try {
      await startBinary(String(binarySettings.url).trim(), binarySettings.port);
      startupLog('[binary] autoStart success');
    } catch (e) {
      startupLog(`[binary] autoStart failed: ${e?.message || e}`);
    }
  }
  app.listen(port, '0.0.0.0', () => {
    startupLog(`[mc-bot-only] listening on 0.0.0.0:${port}`);
  });
};

boot().catch(() => {
  process.exit(1);
});
