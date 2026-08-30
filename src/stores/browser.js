import { ref } from 'vue'

export const browserStatus = ref(false)
export const loginStatus = ref(false)
export const friendsList = ref([])

export const setBrowserStatus = (status) => {
  browserStatus.value = status
}

export const setLoginStatus = (status) => {
  loginStatus.value = status
}

export const setFriendsList = (list) => {
  friendsList.value = list
}
