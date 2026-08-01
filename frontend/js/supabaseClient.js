// Requires the supabase-js CDN script to be loaded before this file.
const supabaseClient = supabase.createClient(APP_CONFIG.SUPABASE_URL, APP_CONFIG.SUPABASE_ANON_KEY);

async function getAccessToken() {
  const { data } = await supabaseClient.auth.getSession();
  return data.session ? data.session.access_token : null;
}

async function getCurrentSession() {
  const { data } = await supabaseClient.auth.getSession();
  return data.session;
}

async function requireLogin() {
  const session = await getCurrentSession();
  if (!session) {
    window.location.href = "index.html";
  }
  return session;
}

async function logout() {
  await supabaseClient.auth.signOut();
  window.location.href = "index.html";
}
