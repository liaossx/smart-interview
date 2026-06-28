// 简单路由控制
class Router {
    constructor() {
        this.pages = {};
        this.currentPage = null;
    }

    register(name, showFn) {
        this.pages[name] = showFn;
    }

    navigate(name) {
        // 隐藏所有页面
        document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
        // 显示目标页面
        const target = document.getElementById('page-' + name);
        if (target) target.classList.add('active');

        // 更新侧边栏高亮
        document.querySelectorAll('.sidebar .history-item[data-page]').forEach(item => item.classList.remove('active'));
        const sidebarItem = document.querySelector(`.sidebar .history-item[data-page="${name}"]`);
        if (sidebarItem) sidebarItem.classList.add('active');

        if (this.pages[name]) {
            this.pages[name]();
        }
        this.currentPage = name;
    }
}

const router = new Router();

// 页面切换
function showPage(name) {
    router.navigate(name);
}

// 侧边栏点击事件委托
document.addEventListener('click', function(e) {
    const item = e.target.closest('.sidebar .history-item[data-page]');
    if (!item) return;
    const pageName = item.getAttribute('data-page');
    // 先清除所有侧边栏 active，再给当前项加 active
    document.querySelectorAll('.sidebar .history-item[data-page]').forEach(el => el.classList.remove('active'));
    item.classList.add('active');
    router.navigate(pageName);
});
