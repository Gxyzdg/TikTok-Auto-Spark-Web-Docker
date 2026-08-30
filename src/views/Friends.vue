<template>
  <div class="page">
    <div class="page-header animate-fade-in-up">
      <div>
        <div class="page-header__title">好友列表</div>
        <div class="page-header__subtitle">管理你的抖音好友，发送消息或创建定时任务</div>
      </div>
      <div class="page-header__actions">
        <el-button :icon="Refresh" @click="loadFriends" :loading="loading">刷新</el-button>
        <el-button v-if="!selectionMode" type="success" :icon="Tickets" @click="selectionMode = true">
          多选
        </el-button>
        <template v-else>
          <el-button type="success" :icon="Check" @click="openBatchTaskDialog">
            创建定时任务 ({{ selectedFriends.length }})
          </el-button>
          <el-button :icon="Close" @click="cancelSelection">取消</el-button>
        </template>
      </div>
    </div>

    <el-card shadow="never">
      <div class="toolbar">
        <el-input
          v-model="searchKeyword"
          placeholder="搜索好友…"
          :prefix-icon="Search"
          clearable
          style="max-width: 220px"
        />
        <el-select v-model="fireFilter" placeholder="火花筛选" clearable style="width: 140px">
          <el-option label="全部" value="all" />
          <el-option label="有火花" value="has" />
          <el-option label="无火花" value="none" />
        </el-select>
      </div>

      <el-skeleton v-if="loading" :rows="8" animated class="table-skeleton" />
      <template v-else>
        <el-table
          :data="filteredFriends"
          stripe
          @selection-change="handleSelectionChange"
        >
          <el-table-column v-if="selectionMode" type="selection" width="50" />
          <el-table-column type="index" label="序号" :width="selectionMode ? 80 : 60" />
          <el-table-column label="头像" width="80">
            <template #default="{ row }">
              <el-avatar :size="40" :src="row.avatar">
                <el-icon><User /></el-icon>
              </el-avatar>
            </template>
          </el-table-column>
          <el-table-column prop="name" label="昵称" min-width="140" />
          <el-table-column prop="fire" label="火花天数" width="110">
            <template #default="{ row }">
              <el-tag v-if="isFireActive(row.fire)" type="warning">{{ row.fire }}🔥</el-tag>
              <el-tag v-else type="info">无火花</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="110" fixed="right">
            <template #default="{ row }">
              <el-dropdown @command="(cmd) => handleCommand(cmd, row)" trigger="click">
                <el-button type="primary" size="small" plain>
                  操作<el-icon class="el-icon--right"><ArrowDown /></el-icon>
                </el-button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="send">发送消息</el-dropdown-item>
                    <el-dropdown-item command="create">创建任务</el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </template>
          </el-table-column>
        </el-table>

        <el-empty v-if="filteredFriends.length === 0" description="暂无好友数据">
          <el-button type="primary" :icon="Refresh" @click="loadFriends">刷新好友</el-button>
        </el-empty>
      </template>
    </el-card>

    <!-- 发送消息 -->
    <el-dialog v-model="sendDialogVisible" title="发送消息" width="500px" destroy-on-close>
      <el-form :model="sendForm" label-width="80px">
        <el-form-item label="好友">
          <el-input v-model="sendForm.name" disabled />
        </el-form-item>
        <el-form-item label="消息内容">
          <el-input v-model="sendForm.text" type="textarea" :rows="4" placeholder="请输入消息内容" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="sendDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSend" :loading="sendLoading">发送</el-button>
      </template>
    </el-dialog>

    <!-- 创建定时任务 -->
    <el-dialog v-model="taskDialogVisible" title="创建定时任务" width="500px" destroy-on-close>
      <el-form ref="taskFormRef" :model="taskForm" :rules="taskRules" label-width="80px">
        <el-form-item label="好友">
          <el-input v-model="taskForm.name" disabled />
        </el-form-item>
        <el-form-item label="执行时间" prop="time">
          <el-time-picker v-model="taskForm.time" format="HH:mm" value-format="HH:mm" placeholder="选择时间" style="width: 100%" />
        </el-form-item>
        <el-form-item label="消息内容">
          <el-input v-model="taskForm.text" type="textarea" :rows="3" placeholder="留空将使用每日名言" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="taskDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleCreateTask" :loading="taskLoading">创建</el-button>
      </template>
    </el-dialog>

    <!-- 批量创建 -->
    <el-dialog v-model="batchTaskDialogVisible" title="批量创建定时任务" width="600px" destroy-on-close>
      <div class="selected-friends">
        <span class="label">已选好友 ({{ selectedFriends.length }})：</span>
        <el-tag v-for="f in selectedFriends" :key="f.name" class="friend-tag">{{ f.name }}</el-tag>
        <span v-if="selectedFriends.length === 0" class="empty-hint">未选择任何好友</span>
      </div>
      <el-divider />
      <el-form ref="batchTaskFormRef" :model="batchTaskForm" :rules="taskRules" label-width="80px">
        <el-form-item label="执行时间" prop="time">
          <el-time-picker v-model="batchTaskForm.time" format="HH:mm" value-format="HH:mm" placeholder="选择时间" style="width: 100%" />
        </el-form-item>
        <el-form-item label="消息内容">
          <el-input v-model="batchTaskForm.text" type="textarea" :rows="3" placeholder="留空将使用每日名言" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="batchTaskDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleBatchCreateTask" :loading="batchTaskLoading">
          批量创建 ({{ selectedFriends.length }})
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh, Search, User, ArrowDown, Tickets, Check, Close } from '@element-plus/icons-vue'
import { sendMessage, addTask, getFriendsList } from '../api/douyin'
import { friendsList, setFriendsList } from '../stores/browser'
import { formatFriendsList } from '../utils/format'

const loading = ref(false)
const searchKeyword = ref('')
const fireFilter = ref('')

// 判断是否有火花：数值>0 或文本非空非"0"
const isFireActive = (fire) => {
  if (!fire) return false
  const n = Number(fire)
  return !isNaN(n) ? n > 0 : true
}

const sendDialogVisible = ref(false)
const sendLoading = ref(false)
const sendForm = ref({
  name: '',
  text: ''
})

const taskDialogVisible = ref(false)
const taskLoading = ref(false)
const taskForm = ref({
  name: '',
  time: '',
  text: ''
})

const selectionMode = ref(false)
const selectedFriends = ref([])
const batchTaskDialogVisible = ref(false)
const batchTaskLoading = ref(false)
const batchTaskForm = ref({
  time: '',
  text: ''
})

const taskFormRef = ref(null)
const batchTaskFormRef = ref(null)

const taskRules = {
  time: [{ required: true, message: '请选择执行时间', trigger: 'change' }]
}

const filteredFriends = computed(() => {
  let list = friendsList.value

  if (searchKeyword.value) {
    const keyword = searchKeyword.value.toLowerCase()
    list = list.filter(f => f.name.toLowerCase().includes(keyword))
  }

  if (fireFilter.value && fireFilter.value !== 'all') {
    list = list.filter(f => {
      if (fireFilter.value === 'has') return isFireActive(f.fire)
      if (fireFilter.value === 'none') return !isFireActive(f.fire)
      return false
    })
  }

  return list
})

// 刷新按钮 - 请求 API 获取最新数据
const loadFriends = async () => {
  loading.value = true
  try {
    const res = await getFriendsList()
    setFriendsList(formatFriendsList(res.data.list))
  } catch (error) {
    // 错误提示已由响应拦截器统一处理
  } finally {
    loading.value = false
  }
}

const openSendDialog = (friend) => {
  sendForm.value = {
    name: friend.name,
    text: ''
  }
  sendDialogVisible.value = true
}

const handleSend = async () => {
  if (sendLoading.value) return
  if (!sendForm.value.text.trim()) {
    ElMessage.warning('请输入消息内容')
    return
  }

  try {
    await ElMessageBox.confirm(`确定要发送消息给「${sendForm.value.name}」吗？`, '发送消息', {
      type: 'warning'
    })
  } catch {
    return
  }

  sendLoading.value = true
  try {
    const res = await sendMessage(sendForm.value.name, sendForm.value.text)
    ElMessage.success('发送成功')
    sendDialogVisible.value = false
  } catch (error) {
    // 错误已由响应拦截器统一提示
  } finally {
    sendLoading.value = false
  }
}

const handleCommand = (command, row) => {
  if (command === 'send') {
    openSendDialog(row)
  } else if (command === 'create') {
    openCreateTaskDialog(row)
  }
}

const openCreateTaskDialog = (friend) => {
  taskForm.value = {
    name: friend.name,
    time: '',
    text: ''
  }
  taskDialogVisible.value = true
}

const handleCreateTask = async () => {
  if (taskLoading.value) return
  if (!taskFormRef.value) return
  try {
    await taskFormRef.value.validate()
  } catch {
    return
  }

  taskLoading.value = true
  try {
    await addTask(taskForm.value.time, taskForm.value.name, taskForm.value.text || null)
    ElMessage.success('创建成功')
    taskDialogVisible.value = false
  } catch (error) {
    // 错误已由响应拦截器统一提示
  } finally {
    taskLoading.value = false
  }
}

const handleSelectionChange = (rows) => {
  selectedFriends.value = rows
}

const cancelSelection = () => {
  selectionMode.value = false
  selectedFriends.value = []
}

const openBatchTaskDialog = () => {
  if (selectedFriends.value.length === 0) {
    ElMessage.warning('请先选择好友')
    return
  }
  batchTaskForm.value = { time: '', text: '' }
  batchTaskDialogVisible.value = true
}

const handleBatchCreateTask = async () => {
  if (batchTaskLoading.value) return
  if (!batchTaskFormRef.value) return
  try {
    await batchTaskFormRef.value.validate()
  } catch {
    return
  }

  try {
    await ElMessageBox.confirm(
      `将为选中的 ${selectedFriends.value.length} 位好友创建定时任务，是否继续？`,
      '批量创建',
      { type: 'warning' }
    )
  } catch {
    return
  }

  batchTaskLoading.value = true
  let success = 0
  let failed = 0
  try {
    for (const friend of selectedFriends.value) {
      try {
        await addTask(batchTaskForm.value.time, friend.name, batchTaskForm.value.text || null)
        success++
      } catch {
        failed++
      }
    }
    if (failed === 0) {
      ElMessage.success(`批量创建成功，共 ${success} 个任务`)
    } else {
      ElMessage.warning(`完成：成功 ${success} 个，失败 ${failed} 个`)
    }
    batchTaskDialogVisible.value = false
    cancelSelection()
  } finally {
    batchTaskLoading.value = false
  }
}

// 进入页面时，若好友列表为空则自动加载
onMounted(() => {
  if (friendsList.value.length === 0) {
    loadFriends()
  }
})
</script>

<style scoped>
.page {
  max-width: 1280px;
  margin: 0 auto;
}

.selected-friends {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  max-height: 120px;
  overflow-y: auto;
}

.selected-friends .label {
  font-weight: 500;
  color: var(--text-2);
  white-space: nowrap;
}

.friend-tag {
  margin: 0;
}

.selected-friends .empty-hint {
  color: var(--text-3);
  font-size: 14px;
}
</style>
