(() => {
    const request = window.requestAnimationFrame.bind(window);
    const cancel = window.cancelAnimationFrame.bind(window);
    const pending = new Map();
    let sequence = 0;

    // 被遮挡的 WebGL 页面仍需低频处理输入与本机 HTTP 完成事件。
    window.requestAnimationFrame = callback => {
        const id = ++sequence;
        const frame = { native: null, timer: null };
        pending.set(id, frame);
        const finish = timestamp => {
            if (!pending.delete(id)) return;
            clearTimeout(frame.timer);
            if (frame.native !== null) cancel(frame.native);
            callback(timestamp);
        };
        frame.native = request(finish);
        frame.timer = setTimeout(() => finish(performance.now()), 250);
        return id;
    };

    window.cancelAnimationFrame = id => {
        const frame = pending.get(id);
        if (!frame) return;
        pending.delete(id);
        clearTimeout(frame.timer);
        if (frame.native !== null) cancel(frame.native);
    };
})();
