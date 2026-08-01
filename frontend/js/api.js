async function apiRequest(path, { method = "GET", body = null } = {}) {
  const token = await getAccessToken();
  const headers = { "Content-Type": "application/json" };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${APP_CONFIG.API_BASE_URL}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : null,
  });

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const errJson = await res.json();
      detail = errJson.detail || detail;
    } catch (_) {}
    throw new Error(detail);
  }
  return res.json();
}

const api = {
  listCourses: () => apiRequest("/courses"),
  createCourse: (data) => apiRequest("/courses", { method: "POST", body: data }),
  listLessons: (courseId) => apiRequest(`/courses/${courseId}/lessons`),
  createLesson: (courseId, data) => apiRequest(`/courses/${courseId}/lessons`, { method: "POST", body: data }),
  approveLesson: (lessonId) => apiRequest(`/courses/lessons/${lessonId}/approve`, { method: "PATCH" }),
  enroll: (courseId) => apiRequest(`/courses/${courseId}/enroll`, { method: "POST" }),

  listJobs: () => apiRequest("/jobs"),

  submitWork: (lessonId, content) => apiRequest("/submissions", { method: "POST", body: { lesson_id: lessonId, content } }),
  mySubmissions: () => apiRequest("/submissions/me"),
  allSubmissions: () => apiRequest("/submissions"),

  mentorChat: (message) => apiRequest("/mentor/chat", { method: "POST", body: { message } }),
  mentorHistory: () => apiRequest("/mentor/history"),
};
