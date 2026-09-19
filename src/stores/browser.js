import { ref } from 'vue'

export const browserStatus = ref(false)
export const loginStatus = ref(false)
export const friendsList = ref([])
export const douyinAvatar = ref('')      // 当前登录抖音账号头像
export const douyinNickname = ref('')    // 当前登录抖音账号昵称

export const setBrowserStatus = (status) => {
  browserStatus.value = status
}

export const setLoginStatus = (status) => {
  loginStatus.value = status
}

export const setFriendsList = (list) => {
  friendsList.value = list
}

export const setDouyinUser = (nickname, avatar) => {
  douyinNickname.value = nickname || ''
  douyinAvatar.value = avatar || ''
}
