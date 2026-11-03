import { useState } from 'react';

export type Connection = {
  status: 'not_connected' | 'connected' | 'disconnected';
  port: number;
  handoff_prompt: string;
};

export function hostLabel(connection?: Connection) {
  if (!connection) return '主持信息不可用';
  return { not_connected: '主持尚未接入', connected: '主持近期在线', disconnected: '主持连接已超时' }[connection.status];
}

export function HostConnection({ connection, online }: { connection?: Connection; online: boolean }) {
  const [copyState, setCopyState] = useState('');
  async function copy() {
    if (!connection) return;
    try {
      await navigator.clipboard.writeText(connection.handoff_prompt);
      setCopyState('已复制，请粘贴到 Codex 发送；复制本身不会连接主持。');
    } catch {
      setCopyState('复制未成功，请选中下方文本手动复制。');
    }
  }
  return <section className="host-connection">
    <p role="status">网页服务：{online ? '已连接' : '连接中断，正在重连'}<br />
      Codex 主持：{online ? hostLabel(connection) : '状态暂不可确认'}</p>
    {!connection ? <p>当前服务尚未提供接管信息。请在原终端停止旧服务，使用相同存档路径与端口重新启动新版服务；无需重建牌局。</p> : <>
      <ol>
        <li>复制下方接管文本。</li>
        <li>粘贴到当前 Codex 会话并发送。</li>
        <li>Codex 接入后，回到牌桌等待对手行动；轮到你时按钮会出现。</li>
      </ol>
      <p>网页无法自动唤醒 Codex。刷新页面或只在终端运行一次桥接命令，不会启动自动对手。</p>
      <button className="primary" disabled={!online} onClick={copy}>复制接管文本</button>
      <p className="copy-status" role="status">{copyState}</p>
      <label htmlFor="host-prompt">发送给 Codex 的文本</label>
      <textarea id="host-prompt" readOnly value={connection.handoff_prompt} rows={10} />
      <p className="muted">接管文本仅包含本机目录、牌桌路径和端口，不包含主持凭据或底牌。主持状态根据最近 65 秒的请求判断，不保证会话仍在执行；超时后可重新发送同一段文本恢复。</p>
    </>}
  </section>;
}
