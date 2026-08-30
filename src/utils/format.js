// 好友列表数据格式化工具
// 后端返回的 list 形如 { 昵称: [头像, 火花天数], ... }
export function formatFriendsList(list) {
  const source = list || {}
  return Object.entries(source).map(([name, [avatar, fire]]) => ({
    name,
    avatar,
    fire
  }))
}
