"""
独立轻量级微信风格 Web 测试面板
无需额外安装庞大前端框架或 Gradio，基于标准库直接启动原生 HTTP 服务
集成了：
1. 实时数字人微信对话与 TTS 语音播放
2. 父亲生平档案与生活习惯表单编辑 (Profile)
3. 家庭情境记忆库手动录入与管理 (Episodic Memories)
4. 对话中自动唤醒与动态记忆沉淀 (Dynamic Recall & Auto Consolidation)
5. 1463 条父亲真实历史原声试听珍藏库
"""

import http.server
import json
import os
from pathlib import Path
import socketserver
import urllib.parse
from typing import Any, Dict

from modules.config_loader import load_config
from modules.bot.gateway import BotGateway

HTML_PAGE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>绿色聊天软件数字人与生平记忆系统 (Memorial Bot)</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif; }
        body { background: #ededed; display: flex; height: 100vh; overflow: hidden; }
        
        /* 侧边信息栏 */
        .sidebar { width: 380px; background: #f7f7f7; border-right: 1px solid #e0e0e0; display: flex; flex-direction: column; }
        .sidebar-tabs { display: flex; background: #eaeaea; border-bottom: 1px solid #ddd; }
        .tab-btn { flex: 1; padding: 12px 8px; border: none; background: transparent; cursor: pointer; font-size: 13px; font-weight: 600; color: #666; transition: all 0.2s; }
        .tab-btn.active { background: #f7f7f7; color: #07c160; border-bottom: 2px solid #07c160; }
        
        .sidebar-content { flex: 1; padding: 15px; overflow-y: auto; font-size: 13px; color: #555; }
        .card { background: white; border-radius: 8px; padding: 14px; margin-bottom: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.06); }
        .card-title { font-weight: 600; color: #222; margin-bottom: 8px; font-size: 14px; display: flex; justify-content: space-between; align-items: center; }
        
        /* 表单输入控件 */
        .form-group { margin-bottom: 10px; }
        .form-label { display: block; font-size: 12px; font-weight: 600; color: #555; margin-bottom: 4px; }
        .form-input, .form-textarea { width: 100%; padding: 8px 10px; border: 1px solid #ddd; border-radius: 5px; font-size: 13px; outline: none; background: #fafafa; }
        .form-input:focus, .form-textarea:focus { border-color: #07c160; background: #fff; }
        .form-textarea { resize: vertical; min-height: 60px; }
        .btn-green { background: #07c160; color: white; border: none; padding: 8px 14px; border-radius: 5px; font-size: 13px; cursor: pointer; font-weight: 500; transition: background 0.2s; }
        .btn-green:hover { background: #06ad56; }
        .btn-green:disabled { background: #a5d6a7; cursor: not-allowed; }
        .btn-del { background: transparent; color: #e53935; border: none; cursor: pointer; font-size: 12px; padding: 2px 6px; border-radius: 4px; }
        .btn-del:hover { background: #ffebee; }

        .memory-item { background: #fafafa; border: 1px solid #eee; border-radius: 6px; padding: 10px; margin-bottom: 8px; position: relative; }
        .memory-item-title { font-weight: 600; color: #111; font-size: 13px; display: flex; justify-content: space-between; align-items: center; }
        .memory-item-period { font-size: 11px; color: #888; margin-top: 2px; }
        .memory-item-content { font-size: 12px; color: #444; margin-top: 6px; line-height: 1.5; }
        .memory-tags { margin-top: 6px; display: flex; flex-wrap: wrap; gap: 4px; }
        .memory-tag { display: inline-block; background: #e8f4d9; color: #4b820a; font-size: 11px; padding: 1px 6px; border-radius: 3px; }

        .voice-item { background: white; border-radius: 8px; padding: 10px; margin-bottom: 8px; box-shadow: 0 1px 2px rgba(0,0,0,0.04); display: flex; flex-direction: column; gap: 4px; }
        .voice-meta { font-size: 11px; color: #888; display: flex; justify-content: space-between; }
        .voice-play { margin-top: 4px; width: 100%; height: 28px; }

        /* 主聊天窗口 */
        .chat-container { flex: 1; display: flex; flex-direction: column; background: #f5f5f5; }
        .chat-header { height: 60px; background: #ebebeb; border-bottom: 1px solid #dedede; display: flex; align-items: center; justify-content: space-between; padding: 0 20px; }
        .chat-header .title { font-size: 17px; font-weight: 600; color: #111; }
        .chat-header .status { font-size: 12px; color: #07c160; margin-left: 8px; }

        .chat-messages { flex: 1; overflow-y: auto; padding: 20px; display: flex; flex-direction: column; gap: 16px; }
        
        /* 气泡样式 */
        .msg-row { display: flex; align-items: flex-start; gap: 10px; max-width: 82%; }
        .msg-row.father { align-self: flex-start; }
        .msg-row.user { align-self: flex-end; flex-direction: row-reverse; }

        .avatar { width: 42px; height: 42px; border-radius: 6px; display: flex; align-items: center; justify-content: center; font-weight: bold; color: white; flex-shrink: 0; font-size: 14px; }
        .avatar.father { background: #5b7da8; }
        .avatar.user { background: #07c160; }

        .bubble { padding: 10px 14px; border-radius: 8px; font-size: 15px; line-height: 1.5; word-break: break-word; position: relative; }
        .father .bubble { background: #ffffff; color: #111; border: 1px solid #e5e5e5; }
        .user .bubble { background: #95ec69; color: #000; }

        .bubble-recall { margin-top: 6px; font-size: 11px; color: #4b820a; background: #eef7e6; border-radius: 4px; padding: 3px 8px; display: inline-flex; align-items: center; gap: 4px; }
        .audio-player-box { margin-top: 8px; display: flex; align-items: center; gap: 8px; }

        /* 记忆沉淀提示条 */
        .memory-learned-banner { align-self: center; background: #fef8e7; border: 1px solid #fae29c; border-radius: 20px; padding: 6px 16px; font-size: 12px; color: #8a6d3b; display: flex; align-items: center; gap: 6px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); animation: fadeIn 0.4s ease-in-out; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: translateY(0); } }

        /* 输入栏 */
        .chat-input-area { background: #f7f7f7; border-top: 1px solid #e0e0e0; padding: 15px 20px; display: flex; flex-direction: column; gap: 10px; }
        .input-controls { display: flex; align-items: center; justify-content: space-between; font-size: 13px; color: #666; }
        .input-box-wrapper { display: flex; gap: 12px; }
        .chat-input { flex: 1; padding: 12px 14px; border: 1px solid #ddd; border-radius: 6px; font-size: 15px; outline: none; background: white; }
        .chat-input:focus { border-color: #07c160; }
        .send-btn { background: #07c160; color: white; border: none; padding: 0 24px; border-radius: 6px; font-size: 15px; cursor: pointer; font-weight: 500; }
        .send-btn:hover { background: #06ad56; }
        .send-btn:disabled { background: #a5d6a7; cursor: not-allowed; }

        .toast { position: fixed; bottom: 80px; left: 50%; transform: translateX(-50%); background: rgba(0,0,0,0.75); color: white; padding: 8px 18px; border-radius: 20px; font-size: 13px; z-index: 1000; opacity: 0; transition: opacity 0.3s; pointer-events: none; }
        .toast.show { opacity: 1; }
    </style>
</head>
<body>
    <!-- 左侧信息与记忆维护栏 -->
    <div class="sidebar">
        <div class="sidebar-tabs">
            <button class="tab-btn active" onclick="switchTab('profile')">生平画像</button>
            <button class="tab-btn" onclick="switchTab('memories')">生平记忆库</button>
            <button class="tab-btn" onclick="switchTab('voice')">历史原声库</button>
        </div>

        <!-- 1. 生平画像编辑标签页 -->
        <div class="sidebar-content" id="tab-profile">
            <div class="card">
                <div class="card-title">父亲档案与习惯特征</div>
                <div class="form-group">
                    <label class="form-label">姓名</label>
                    <input type="text" id="prof-name" class="form-input" placeholder="父亲姓名">
                </div>
                <div class="form-group">
                    <label class="form-label">籍贯 / 家乡</label>
                    <input type="text" id="prof-hometown" class="form-input" placeholder="例如：浙江温州">
                </div>
                <div class="form-group">
                    <label class="form-label">生平工作 / 职业经历</label>
                    <input type="text" id="prof-occupation" class="form-input" placeholder="例如：机械加工、厂里老师傅">
                </div>
                <div class="form-group">
                    <label class="form-label">年龄或生日</label>
                    <input type="text" id="prof-age" class="form-input" placeholder="例如：58岁 / 10月出生">
                </div>
                <div class="form-group">
                    <label class="form-label">兴趣喜好 (逗号分隔)</label>
                    <input type="text" id="prof-hobbies" class="form-input" placeholder="喝茶, 散步, 看新闻, 做饭">
                </div>
                <div class="form-group">
                    <label class="form-label">饮食口味与喜爱的菜 (逗号分隔)</label>
                    <input type="text" id="prof-foods" class="form-input" placeholder="清淡, 红烧肉, 绿茶, 豆腐">
                </div>
                <div class="form-group">
                    <label class="form-label">生活习惯与作息 (逗号分隔)</label>
                    <input type="text" id="prof-habits" class="form-input" placeholder="早起晨练, 饭后散步, 睡前看手机">
                </div>
                <div class="form-group">
                    <label class="form-label">平时最挂念的事情 (逗号分隔)</label>
                    <input type="text" id="prof-care" class="form-input" placeholder="工作压力, 身体健康, 按时吃饭, 出行安全">
                </div>
                <div class="form-group">
                    <label class="form-label">对我的称呼</label>
                    <input type="text" id="prof-nickname" class="form-input" placeholder="小明">
                </div>
                <button class="btn-green" style="width: 100%; margin-top: 6px;" onclick="saveProfile()">💾 保存画像修改</button>
            </div>

            <div class="card">
                <div class="card-title">真实绿色聊天软件语言学特征 (已植入)</div>
                <div style="font-size: 12px; line-height: 1.6; color: #444;">
                    • <b>平均字数</b>: 10~15 字 / 条 (短促生活化)<br>
                    • <b>核心高频词</b>: [OK]、知道了、噢、好的、[强]<br>
                    • <b>标点习惯</b>: 逗号占主导，极少长句，不讲大道理<br>
                    • <b>问答对话库</b>: 支持少样本真实历史问答对自动唤醒
                </div>
            </div>
        </div>

        <!-- 2. 生平记忆库与手动录入标签页 -->
        <div class="sidebar-content" id="tab-memories" style="display: none;">
            <div class="card">
                <div class="card-title">✍️ 手动录入一段生平往事</div>
                <div class="form-group">
                    <label class="form-label">事件标题 (8字内)</label>
                    <input type="text" id="mem-title" class="form-input" placeholder="例如：高考送考那天下大雨">
                </div>
                <div class="form-group">
                    <label class="form-label">发生时间 / 时期</label>
                    <input type="text" id="mem-period" class="form-input" placeholder="例如：2015年夏天 或 小时候">
                </div>
                <div class="form-group">
                    <label class="form-label">往事详情与真实生活细节</label>
                    <textarea id="mem-content" class="form-textarea" placeholder="详细写下这件事的真实过程，如：当年家里翻修老屋，长辈每天早起去建材市场挑砖瓦，衣服湿透了还特地在院子角落留了块地让我种花..."></textarea>
                </div>
                <div class="form-group">
                    <label class="form-label">关联关键词标签 (逗号分隔)</label>
                    <input type="text" id="mem-tags" class="form-input" placeholder="老屋, 盖房, 院子, 种花">
                </div>
                <button class="btn-green" style="width: 100%;" onclick="addMemory()">＋ 存入生平记忆库</button>
            </div>

            <div class="card">
                <div class="card-title">
                    <span>已收录的情境回忆</span>
                    <span id="mem-count" style="font-size: 11px; color: #888; font-weight: normal;"></span>
                </div>
                <div id="memory-list-container">正在加载记忆库...</div>
            </div>
        </div>

        <!-- 3. 真实原声音频标签页 -->
        <div class="sidebar-content" id="tab-voice" style="display: none;">
            <div style="font-weight: 600; margin-bottom: 10px; color: #333;">亲友真实历史语音选萃 (已解码WAV)：</div>
            <div id="voice-list">正在加载音频清单...</div>
        </div>
    </div>

    <!-- 主聊天窗口 -->
    <div class="chat-container">
        <div class="chat-header">
            <div>
                <span class="title">数字人亲友 (纪念中)</span>
                <span class="status">● 在线</span>
            </div>
            <button onclick="clearHistory()" style="border:none; background:transparent; color:#888; cursor:pointer; font-size:13px;">清空对话</button>
        </div>

        <div class="chat-messages" id="messages">
            <div class="msg-row father">
                <div class="avatar father">父</div>
                <div class="bubble">在忙什么呢？今天饭吃过了没。</div>
            </div>
        </div>

        <div class="chat-input-area">
            <div class="input-controls">
                <label style="cursor: pointer; display: flex; align-items: center; gap: 6px;">
                    <input type="checkbox" id="voiceToggle" checked> 合成语音回复 (TTS)
                </label>
                <span>按 Enter 键发送</span>
            </div>
            <div class="input-box-wrapper">
                <input type="text" id="userInput" class="chat-input" placeholder="给父亲发微信消息（例如问候生活、或者提起往事...）" autofocus>
                <button id="sendBtn" class="send-btn" onclick="sendMessage()">发送</button>
            </div>
        </div>
    </div>

    <div id="toast" class="toast"></div>

    <script>
        const input = document.getElementById('userInput');
        const sendBtn = document.getElementById('sendBtn');
        const messagesDiv = document.getElementById('messages');
        const voiceToggle = document.getElementById('voiceToggle');

        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendMessage();
            }
        });

        function showToast(msg) {
            const t = document.getElementById('toast');
            t.textContent = msg;
            t.classList.add('show');
            setTimeout(() => t.classList.remove('show'), 2500);
        }

        function switchTab(tab) {
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            document.getElementById('tab-profile').style.display = tab === 'profile' ? 'block' : 'none';
            document.getElementById('tab-memories').style.display = tab === 'memories' ? 'block' : 'none';
            document.getElementById('tab-voice').style.display = tab === 'voice' ? 'block' : 'none';
            
            const btnIdx = tab === 'profile' ? 0 : (tab === 'memories' ? 1 : 2);
            document.querySelectorAll('.tab-btn')[btnIdx].classList.add('active');

            if (tab === 'voice' && !window.voicesLoaded) {
                loadHistoricalVoices();
            }
        }

        async function fetchProfileAndMemories() {
            try {
                const res = await fetch('/api/profile');
                const data = await res.json();
                const p = data.profile || {};
                
                document.getElementById('prof-name').value = p.name || '';
                document.getElementById('prof-hometown').value = p.hometown || '';
                document.getElementById('prof-occupation').value = p.occupation || '';
                document.getElementById('prof-age').value = p.birthday_or_age || '';
                document.getElementById('prof-hobbies').value = (p.hobbies || []).join(', ');
                document.getElementById('prof-foods').value = (p.favorite_foods || []).join(', ');
                document.getElementById('prof-habits').value = (p.special_habits || []).join(', ');
                document.getElementById('prof-care').value = (p.care_topics || []).join(', ');
                document.getElementById('prof-nickname').value = (p.common_nicknames && p.common_nicknames.user) || '小明';

                renderMemories(data.memories || []);
            } catch(e) {
                console.error(e);
            }
        }
        fetchProfileAndMemories();

        function renderMemories(mems) {
            const container = document.getElementById('memory-list-container');
            document.getElementById('mem-count').textContent = `共 ${mems.length} 条回忆`;
            container.innerHTML = '';
            if (!mems || mems.length === 0) {
                container.innerHTML = '<div style="color:#999; text-align:center; padding: 20px;">记忆库暂空，可在上方添加往事故事</div>';
                return;
            }

            mems.slice().reverse().forEach(m => {
                const div = document.createElement('div');
                div.className = 'memory-item';
                div.innerHTML = `
                    <div class="memory-item-title">
                        <span>《${m.title}》</span>
                        <button class="btn-del" onclick="deleteMemory(${m.id})">🗑️ 删除</button>
                    </div>
                    ${m.time_period ? `<div class="memory-item-period">时期：${m.time_period}</div>` : ''}
                    <div class="memory-item-content">${m.content}</div>
                    ${m.tags && m.tags.length ? `
                        <div class="memory-tags">
                            ${m.tags.map(t => `<span class="memory-tag">${t}</span>`).join('')}
                        </div>
                    ` : ''}
                `;
                container.appendChild(div);
            });
        }

        async function saveProfile() {
            const parseList = (val) => val.split(/[,，]/).map(s => s.trim()).filter(Boolean);
            const payload = {
                name: document.getElementById('prof-name').value.trim() || '纪念对象 (张长生)',
                hometown: document.getElementById('prof-hometown').value.trim(),
                occupation: document.getElementById('prof-occupation').value.trim(),
                birthday_or_age: document.getElementById('prof-age').value.trim(),
                hobbies: parseList(document.getElementById('prof-hobbies').value),
                favorite_foods: parseList(document.getElementById('prof-foods').value),
                special_habits: parseList(document.getElementById('prof-habits').value),
                care_topics: parseList(document.getElementById('prof-care').value),
                common_nicknames: { user: document.getElementById('prof-nickname').value.trim() || '小明' }
            };

            try {
                const res = await fetch('/api/profile/update', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                if (res.ok) {
                    showToast('父亲生活画像已更新并生效！');
                }
            } catch (e) {
                showToast('保存失败，请检查网络连接');
            }
        }

        async function addMemory() {
            const title = document.getElementById('mem-title').value.trim();
            const content = document.getElementById('mem-content').value.trim();
            const period = document.getElementById('mem-period').value.trim();
            const tags = document.getElementById('mem-tags').value.split(/[,，]/).map(s => s.trim()).filter(Boolean);

            if (!title || !content) {
                alert('请填写记忆标题和详情内容！');
                return;
            }

            try {
                const res = await fetch('/api/memory/add', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ title, content, time_period: period, tags })
                });
                const data = await res.json();
                if (data.status === 'ok') {
                    showToast(`新往事《${title}》已存入生平记忆库！`);
                    document.getElementById('mem-title').value = '';
                    document.getElementById('mem-content').value = '';
                    document.getElementById('mem-period').value = '';
                    document.getElementById('mem-tags').value = '';
                    renderMemories(data.memories);
                }
            } catch (e) {
                showToast('录入失败');
            }
        }

        async function deleteMemory(id) {
            if (!confirm('确定删除这条记忆吗？')) return;
            try {
                const res = await fetch('/api/memory/delete', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ id })
                });
                const data = await res.json();
                if (data.status === 'ok') {
                    showToast('记忆已删除');
                    renderMemories(data.memories);
                }
            } catch (e) {
                showToast('删除失败');
            }
        }

        async function loadHistoricalVoices() {
            try {
                const res = await fetch('/api/historical_voices');
                const list = await res.json();
                window.voicesLoaded = true;
                const container = document.getElementById('voice-list');
                container.innerHTML = '';
                list.slice(0, 30).forEach(v => {
                    const item = document.createElement('div');
                    item.className = 'voice-item';
                    item.innerHTML = `
                        <div class="voice-meta">
                            <span>发给: <b>${v.contact}</b></span>
                            <span>${v.time}</span>
                        </div>
                        <audio controls class="voice-play" src="/api/wav/${encodeURIComponent(v.filename)}"></audio>
                    `;
                    container.appendChild(item);
                });
                if (list.length > 30) {
                    const more = document.createElement('div');
                    more.style.textAlign = 'center';
                    more.style.padding = '10px';
                    more.style.color = '#888';
                    more.textContent = `共 ${list.length} 条原声，已展示前 30 条`;
                    container.appendChild(more);
                }
            } catch(e) {}
        }

        async function sendMessage() {
            const text = input.value.trim();
            if (!text) return;

            appendMessage('user', text);
            input.value = '';
            sendBtn.disabled = true;

            try {
                const res = await fetch('/api/chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        message: text,
                        need_voice: voiceToggle.checked
                    })
                });
                const data = await res.json();

                appendMessage('father', data.text, data.audio_url, data.triggered_memories);

                // 如果在对话中自动唤起并沉淀了新记忆
                if (data.new_memory) {
                    appendMemoryLearnedBanner(data.new_memory);
                    fetchProfileAndMemories();
                }
            } catch (err) {
                appendMessage('father', '网络连接出现了一点问题。');
            } finally {
                sendBtn.disabled = false;
                input.focus();
            }
        }

        function appendMessage(sender, text, audioUrl, triggeredMemories) {
            const row = document.createElement('div');
            row.className = `msg-row ${sender}`;

            const avatar = document.createElement('div');
            avatar.className = `avatar ${sender}`;
            avatar.textContent = sender === 'father' ? '父' : '我';

            const bubble = document.createElement('div');
            bubble.className = 'bubble';
            bubble.textContent = text;

            if (triggeredMemories && triggeredMemories.length > 0) {
                const recallDiv = document.createElement('div');
                recallDiv.className = 'bubble-recall';
                recallDiv.innerHTML = `💭 唤起回忆: ${triggeredMemories.map(m => `《${m}》`).join(' ')}`;
                bubble.appendChild(recallDiv);
            }

            if (audioUrl) {
                const audioBox = document.createElement('div');
                audioBox.className = 'audio-player-box';
                const audioEl = document.createElement('audio');
                audioEl.src = audioUrl;
                audioEl.controls = true;
                audioEl.style.height = '32px';
                audioEl.style.marginTop = '6px';
                audioBox.appendChild(audioEl);
                bubble.appendChild(audioBox);
                audioEl.play().catch(() => {});
            }

            row.appendChild(avatar);
            row.appendChild(bubble);
            messagesDiv.appendChild(row);
            messagesDiv.scrollTop = messagesDiv.scrollHeight;
        }

        function appendMemoryLearnedBanner(mem) {
            const banner = document.createElement('div');
            banner.className = 'memory-learned-banner';
            banner.innerHTML = `✨ 父亲记住了这段新回忆：《<b>${mem.title}</b>》已永久沉淀入记忆库！`;
            messagesDiv.appendChild(banner);
            messagesDiv.scrollTop = messagesDiv.scrollHeight;
        }

        async function clearHistory() {
            if (confirm('确认清空当前对话记录吗？')) {
                await fetch('/api/clear', { method: 'POST' });
                messagesDiv.innerHTML = '';
            }
        }
    </script>
</body>
</html>
"""


class WeChatHTTPHandler(http.server.SimpleHTTPRequestHandler):
    """处理 Web UI 交互请求"""

    gateway: BotGateway = None

    def do_GET(self):
        url = urllib.parse.urlparse(self.path)

        if url.path in ["/", "/index.html"]:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_PAGE.encode("utf-8"))
            return

        if url.path == "/api/profile":
            data = {
                "profile": self.gateway.memory_manager.profile,
                "memories": self.gateway.memory_manager.episodic_memories,
                "memories_count": len(self.gateway.memory_manager.episodic_memories),
                "qa_count": len(self.gateway.memory_manager.qa_database),
            }
            self._send_json(data)
            return

        if url.path == "/api/memories":
            self._send_json(self.gateway.memory_manager.episodic_memories)
            return

        if url.path == "/api/historical_voices":
            manifest_file = Path("data/processed/voice_manifest.json")
            voices = []
            if manifest_file.exists():
                with open(manifest_file, "r", encoding="utf-8") as f:
                    raw_voices = json.load(f)
                    for v in raw_voices:
                        if v.get("wav_path"):
                            voices.append({
                                "contact": v.get("contact"),
                                "time": v.get("time"),
                                "filename": os.path.basename(v["wav_path"]),
                            })
            self._send_json(voices)
            return

        if url.path.startswith("/api/wav/"):
            filename = urllib.parse.unquote(os.path.basename(url.path))
            target_file = Path("data/processed/voice_wav") / filename
            if target_file.exists():
                self.send_response(200)
                self.send_header("Content-Type", "audio/wav")
                self.send_header("Content-Length", str(target_file.stat().st_size))
                self.end_headers()
                with open(target_file, "rb") as f:
                    self.wfile.write(f.read())
                return
            else:
                self.send_error(404, "Audio file not found")
                return

        if url.path.startswith("/api/audio/"):
            filename = os.path.basename(url.path)
            audio_dir = Path("data/processed/generated_audio")
            target_file = audio_dir / filename
            if target_file.exists():
                self.send_response(200)
                self.send_header("Content-Type", "audio/wav")
                self.send_header("Content-Length", str(target_file.stat().st_size))
                self.end_headers()
                with open(target_file, "rb") as f:
                    self.wfile.write(f.read())
                return
            else:
                self.send_error(404, "Audio file not found")
                return

        return super().do_GET()

    def do_POST(self):
        url = urllib.parse.urlparse(self.path)

        if url.path == "/api/chat":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            payload = json.loads(body.decode("utf-8"))

            user_msg = payload.get("message", "")
            need_voice = payload.get("need_voice", True)

            result = self.gateway.handle_message(user_msg, need_voice=need_voice)

            audio_url = None
            if result.get("audio_path"):
                audio_name = os.path.basename(result["audio_path"])
                audio_url = f"/api/audio/{audio_name}"

            self._send_json({
                "text": result.get("text", ""),
                "audio_url": audio_url,
                "triggered_memories": result.get("triggered_memories", []),
                "new_memory": result.get("new_memory"),
            })
            return

        if url.path == "/api/profile/update":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            payload = json.loads(body.decode("utf-8"))
            self.gateway.memory_manager.update_profile(payload)
            self._send_json({"status": "ok", "profile": self.gateway.memory_manager.profile})
            return

        if url.path == "/api/memory/add":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            payload = json.loads(body.decode("utf-8"))
            entry = self.gateway.memory_manager.add_memory(
                title=payload.get("title", ""),
                content=payload.get("content", ""),
                time_period=payload.get("time_period", ""),
                tags=payload.get("tags", []),
            )
            self._send_json({
                "status": "ok",
                "entry": entry,
                "memories": self.gateway.memory_manager.episodic_memories,
            })
            return

        if url.path == "/api/memory/delete":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            payload = json.loads(body.decode("utf-8"))
            mem_id = int(payload.get("id", 0))
            self.gateway.memory_manager.delete_memory(mem_id)
            self._send_json({
                "status": "ok",
                "memories": self.gateway.memory_manager.episodic_memories,
            })
            return

        if url.path == "/api/clear":
            self.gateway.clear_history()
            self._send_json({"status": "cleared"})
            return

        self.send_error(404)

    def _send_json(self, data: Dict[str, Any]):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def run_server(port: int = 7860):
    config = load_config()
    gateway = BotGateway(config)
    WeChatHTTPHandler.gateway = gateway

    server_address = ("127.0.0.1", port)
    with socketserver.TCPServer(server_address, WeChatHTTPHandler) as httpd:
        print(f"\n=======================================================")
        print(f" 微信数字人纪念系统 Web 界面已启动")
        print(f" 请使用浏览器访问: http://127.0.0.1:{port}")
        print(f" 按 Ctrl + C 可终止服务")
        print(f"=======================================================\n")
        httpd.serve_forever()


if __name__ == "__main__":
    run_server()
