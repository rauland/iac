const assert = require('node:assert/strict');
const { test } = require('node:test');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const commentPlans = require('./comment-plans.js');

const marker = '<!-- iac-terraform-plan-preview -->';

function fixture(t, { comments = [], head = 'head', state = 'open', body = '## Plan\n~ memory = 2048' } = {}) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'plan-comment-'));
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
  const commentPath = path.join(directory, 'comment.md');
  fs.writeFileSync(commentPath, body);
  const writes = [];
  const listComments = () => {};
  return {
    writes,
    args: {
      env: { PLAN_COMMENT_PATH: commentPath, GITHUB_RUN_ATTEMPT: '2' },
      context: { repo: { owner: 'owner', repo: 'iac' }, runId: 42,
        payload: { pull_request: { number: 9, head: { sha: 'head' } } } },
      core: { info() {} },
      github: {
        paginate: async (method, params) => {
          assert.equal(method, listComments);
          assert.equal(params.issue_number, 9);
          assert.equal(params.per_page, 100);
          return comments;
        },
        rest: {
          pulls: { get: async () => ({ data: { state, head: { sha: head } } }) },
          issues: {
            listComments,
            createComment: async args => writes.push({ operation: 'create', ...args }),
            updateComment: async args => writes.push({ operation: 'update', ...args }),
          },
        },
      },
    },
  };
}

function existing(run = 41, attempt = 1) {
  return { id: 123, user: { login: 'github-actions[bot]' },
    body: `${marker}\n<!-- iac-plan-run:${run}:${attempt} -->\nOld preview` };
}

test('creates one comment with plan text and run identity', async t => {
  const { args, writes } = fixture(t);
  await commentPlans(args);
  assert.equal(writes.length, 1);
  assert.equal(writes[0].operation, 'create');
  assert.equal(writes[0].issue_number, 9);
  assert.match(writes[0].body, /iac-plan-run:42:2/);
  assert.match(writes[0].body, /~ memory = 2048/);
});

test('updates the existing bot comment and leaves human comments alone', async t => {
  const human = { ...existing(), id: 456, user: { login: 'reviewer' } };
  const { args, writes } = fixture(t, { comments: [human, existing()] });
  await commentPlans(args);
  assert.equal(writes.length, 1);
  assert.equal(writes[0].operation, 'update');
  assert.equal(writes[0].comment_id, 123);
});

test('does not replace a newer run or rerun', async t => {
  for (const prior of [existing(43), existing(42, 3)]) {
    const { args, writes } = fixture(t, { comments: [prior] });
    await commentPlans(args);
    assert.equal(writes.length, 0);
  }
});

test('does not publish for a superseded commit or closed PR', async t => {
  for (const options of [{ head: 'new-head' }, { state: 'closed' }]) {
    const { args, writes } = fixture(t, options);
    await commentPlans(args);
    assert.equal(writes.length, 0);
  }
});

test('refuses an oversized comment before calling the write API', async t => {
  const { args, writes } = fixture(t, { body: '🌏'.repeat(20000) });
  await assert.rejects(commentPlans(args), /size limit/);
  assert.equal(writes.length, 0);
});
