<template>
  <div class="page">
    <div class="toolbar animate-fade-in-up">
      <el-button :icon="Refresh" @click="refreshAll" :loading="loading">刷新</el-button>
      <el-button v-if="!selectionMode" type="primary" :icon="Plus" @click="openAddDialog">
        添加任务
      </el-button>
      <el-button
        v-if="!selectionMode && taskList.length > 0"
        type="success"
        :icon="Tickets"
        @click="selectionMode = true"
      >
        多选
      </el-button>
      <template v-else>
        <el-button type="danger" :icon="Delete" @click="handleBatchDelete" :loading="batchDeleteLoading">
          删除 ({{ selectedTasks.length }})
        </el-button>
        <el-button :icon="Close" @click="cancelSelection">取消</el-button>
      </template>
    </div>

    <el-card shadow="never">
      <el-skeleton v-if="loading" :rows="8" animated class="table-skeleton" />
      <template v-else>
        <el-table :data="taskList" stripe @selection-change="handleSelectionChange">
          <el-table-column v-if="selectionMode" type="selection" width="50" />
          <el-table-column type="index" label="序号" :width="selectionMode ? 80 : 60" />
          <el-table-column prop="name" label="好友" min-width="140" />
          <el-table-column label="执行时间" width="110">
            <template #default="{ row }">
              <el-tag type="warning" effect="plain">{{ row.time }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="下次执行" min-width="180">
            <template #default="{ row }">
              <span v-if="row.active" class="next-run">
                <el-icon><Clock /></el-icon>
                {{ row.next_run || '—' }}
              </span>
              <el-tag v-else type="info" effect="plain">已停用</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="270" fixed="right">
            <template #default="{ row }">
              <el-button v-if="row.active" type="warning" size="small" plain @click="openEditDialog(row)">
                修改时间
              </el-button>
              <el-button
                :type="row.active ? 'info' : 'success'"
                size="small"
                plain
                @click="handleToggleTask(row)"
              >
                {{ row.active ? '停用' : '启用' }}
              </el-button>
              <el-button type="danger" size="small" plain @click="handleDelete(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>

        <el-empty v-if="taskList.length === 0" description="暂无定时任务">
          <el-button type="primary" @click="openAddDialog">添加第一个任务</el-button>
        </el-empty>
      </template>
    </el-card>

    <!-- 添加/编辑对话框 -->
    <el-dialog v-model="dialogVisible" :title="dialogTitle" width="500px" destroy-on-close>
      <el-form ref="taskFormRef" :model="taskForm" :rules="taskRules" label-width="80px">
        <el-form-item label="好友" prop="name">
          <el-select
            v-model="taskForm.name"
            placeholder="选择好友"
            filterable
            :disabled="dialogMode === 'edit'"
            style="width: 100%"
          >
            <el-option
              v-for="friend in availableFriends"
              :key="friend.name"
              :label="friend.name"
              :value="friend.name"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="执行时间" prop="time">
          <el-time-picker
            v-model="taskForm.time"
            format="HH:mm"
            value-format="HH:mm"
            placeholder="选择时间"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item v-if="dialogMode === 'add'" label="消息内容">
          <el-input
            v-model="taskForm.text"
            type="textarea"
            :rows="3"
            placeholder="留空将使用每日名言"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSubmit" :loading="submitLoading">
          {{ dialogMode === 'add' ? '添加' : '修改' }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Refresh, Delete, Close, Tickets, Clock } from '@element-plus/icons-vue'
import { getTaskList, addTask, delTask, editTask, getFriendsList, pauseTask, enableTask } from '../api/douyin'
import { friendsList as storeFriendsList, setFriendsList } from '../stores/browser'
import { formatFriendsList } from '../utils/format'

const loading = ref(false)
const taskList = ref([])

const selectionMode = ref(false)
const selectedTasks = ref([])
const batchDeleteLoading = ref(false)

const dialogVisible = ref(false)
const dialogMode = ref('add')
const submitLoading = ref(false)
const taskForm = ref({
  name: '',
  time: '',
  text: ''
})

const taskFormRef = ref(null)
const taskRules = {
  name: [{ required: true, message: '请选择好友', trigger: 'change' }],
  time: [{ required: true, message: '请选择执行时间', trigger: 'change' }]
}

const dialogTitle = computed(() => dialogMode.value === 'add' ? '添加定时任务' : '修改执行时间')

const availableFriends = computed(() => {
  // 过滤掉已有任务的好友
  const existingNames = taskList.value.map(t => t.name)
  return storeFriendsList.value.filter(f => !existingNames.includes(f.name))
})

// 页面加载时获取任务列表
onMounted(async () => {
  await refreshAll()
})

// 刷新按钮 - 同时请求任务列表和好友列表（任一失败不影响另一项）
const refreshAll = async () => {
  loading.value = true
  try {
    const [tasksRes, friendsRes] = await Promise.allSettled([
      getTaskList(),
      getFriendsList()
    ])

    // 更新任务列表
    if (tasksRes.status === 'fulfilled' && tasksRes.value.code === 200) {
      const tasks = tasksRes.value.data.tasks || []
      taskList.value = tasks
    }

    // 更新好友列表到 store
    if (friendsRes.status === 'fulfilled' && friendsRes.value.code === 200) {
      setFriendsList(formatFriendsList(friendsRes.value.data.list))
    }
  } catch (error) {
    // 错误提示已由响应拦截器统一处理
  } finally {
    loading.value = false
  }
}

const openAddDialog = () => {
  dialogMode.value = 'add'
  taskForm.value = {
    name: '',
    time: '',
    text: ''
  }
  dialogVisible.value = true
}

const openEditDialog = (task) => {
  dialogMode.value = 'edit'
  taskForm.value = {
    name: task.name,
    time: task.time,
    text: ''
  }
  dialogVisible.value = true
}

const handleSubmit = async () => {
  if (submitLoading.value) return
  if (!taskFormRef.value) return
  try {
    await taskFormRef.value.validate()
  } catch {
    return
  }

  submitLoading.value = true
  try {
    if (dialogMode.value === 'add') {
      await addTask(taskForm.value.time, taskForm.value.name, taskForm.value.text || null)
      ElMessage.success('添加成功')
    } else {
      await editTask(taskForm.value.name, taskForm.value.time)
      ElMessage.success('修改成功')
    }
    dialogVisible.value = false
    // 使用刷新方法更新任务列表
    await refreshAll()
  } catch (error) {
    // 错误已由响应拦截器统一提示
  } finally {
    submitLoading.value = false
  }
}

const handleDelete = async (task) => {
  try {
    await ElMessageBox.confirm(`确定要删除 ${task.name} 的定时任务吗？`, '提示', {
      type: 'warning'
    })
    await delTask(task.task_id)
    ElMessage.success('删除成功')
    await refreshAll()
  } catch (error) {
    // 取消或错误（错误已由响应拦截器统一提示）
  }
}

const handleToggleTask = async (task) => {
  const action = task.active ? '停用' : '启用'
  try {
    await ElMessageBox.confirm(`确定要${action}「${task.name}」的定时任务吗？`, '提示', {
      type: 'warning'
    })
    if (task.active) {
      await pauseTask(task.task_id)
    } else {
      await enableTask(task.task_id)
    }
    ElMessage.success(`${action}成功`)
    await refreshAll()
  } catch (error) {
    // 取消或错误（错误已由响应拦截器统一提示）
  }
}

const handleSelectionChange = (rows) => {
  selectedTasks.value = rows
}

const cancelSelection = () => {
  selectionMode.value = false
  selectedTasks.value = []
}

const handleBatchDelete = async () => {
  if (selectedTasks.value.length === 0) {
    ElMessage.warning('请先选择要删除的任务')
    return
  }
  try {
    await ElMessageBox.confirm(`确定要删除选中的 ${selectedTasks.value.length} 个任务吗？`, '批量删除', {
      type: 'warning'
    })
    batchDeleteLoading.value = true
    let success = 0
    let failed = 0
    for (const task of selectedTasks.value) {
      try {
        await delTask(task.task_id)
        success++
      } catch {
        failed++
      }
    }
    if (failed === 0) {
      ElMessage.success(`批量删除成功，共 ${success} 个`)
    } else {
      ElMessage.warning(`完成：成功 ${success} 个，失败 ${failed} 个`)
    }
    cancelSelection()
    await refreshAll()
  } catch (error) {
    // 取消或错误（错误已由响应拦截器统一提示）
  } finally {
    batchDeleteLoading.value = false
  }
}
</script>

<style scoped>
.next-run {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--text-2);
  font-size: 13px;
}

.next-run .el-icon {
  color: var(--text-3);
}
</style>
