/**
 * 绿色办公通信软件 (WeCom Agent) 消息网关防刷屏合并回复与语音管线逻辑补丁
 * 
 * 核心机制说明：
 * 1. 连续消息防刷屏合并 (Debounce & Aggregation):
 *    用户在日常微信交流中，往往会在短时间内连续发送多条短句、多张照片或短视频。
 *    若机器人每条都独立回复，会导致回复割裂、刷屏且极不自然。
 *    本模块通过滑动时间窗口 (如 3.5~5 秒) 收集用户连续发送的消息队列，
 *    在用户发送间隙将上下文打包合并为单一完整意图送入大模型，最终仅作 1~2 次有温度的自然回复。
 * 
 * 2. 多模态视觉记忆归档优先 (Visual Grounding & Photo Memory):
 *    对于图片与视频类消息，优先调用多模态模型结合本地底座相册 (Family Anchors)
 *    识别画面人物与场景，将其转化为结构化记忆后存入 Memory 库，再作温柔反馈。
 * 
 * 3. 意图驱动双向语音生成 (Contextual Voice Delivery):
 *    检测用户是否发来语音，或文本中是否包含听语音诉求 (如“发条语音”、“听听你声音”)，
 *    自动触发 memorial_tts.py 压制原生 12.2kbps AMR 文件发送回手机。
 */

// 示例：核心防抖与会话队列逻辑伪代码与生产实现参考
const DEBOUNCE_WINDOW_MS = 4000;
const pendingUserQueues = new Map(); // userId -> { timer, messages: [] }

export function queueInboundMessage(userId, messageItem, dispatchCallback) {
    if (!pendingUserQueues.has(userId)) {
        pendingUserQueues.set(userId, {
            timer: null,
            messages: []
        });
    }

    const entry = pendingUserQueues.get(userId);
    entry.messages.push(messageItem);

    // 重置防抖计时器
    if (entry.timer) {
        clearTimeout(entry.timer);
    }

    entry.timer = setTimeout(async () => {
        const batch = [...entry.messages];
        pendingUserQueues.delete(userId);

        try {
            // 合并消息文本与多模态图片/视频描述
            const aggregatedPrompt = buildAggregatedPrompt(batch);
            const shouldReplyVoice = batch.some(m => m.type === 'voice' || /(语音|声音|听听|说句话)/.test(m.text || ''));

            // 执行下游大模型推理与回复
            await dispatchCallback({
                userId,
                prompt: aggregatedPrompt,
                shouldVoice: shouldReplyVoice,
                rawBatch: batch
            });
        } catch (err) {
            console.error('[Debounce Error] 处理合并批次失败:', err);
        }
    }, DEBOUNCE_WINDOW_MS);
}

function buildAggregatedPrompt(messages) {
    if (messages.length === 1) {
        return messages[0].text || messages[0].caption || '';
    }

    const lines = [];
    let imgCount = 0;
    messages.forEach((m, idx) => {
        if (m.type === 'text' || m.type === 'voice') {
            lines.push(`消息 ${idx + 1}: ${m.text}`);
        } else if (m.type === 'image') {
            imgCount++;
            lines.push(`[用户发送了一张照片: ${m.imagePath || '照片'}]`);
        }
    });

    if (imgCount > 0) {
        lines.push(`(注意：用户在短时间内连续发来了上述内容与 ${imgCount} 张照片，请结合整体内容做自然、亲切的综合回复，不要一条条机械回应)`);
    }
    return lines.join('\n');
}
