// Run by actions/github-script after all expected plan results have been validated.
const fs = require('node:fs');

module.exports = async ({ github, context, core, env = process.env }) => {
  const { owner, repo } = context.repo;
  const issue_number = context.payload.pull_request.number;
  const { data: pull } = await github.rest.pulls.get({ owner, repo, pull_number: issue_number });
  if (pull.state !== 'open' || pull.head.sha !== context.payload.pull_request.head.sha) {
    core.info('Skipping plan comment for a closed or superseded pull request.');
    return;
  }

  const marker = '<!-- iac-terraform-plan-preview -->';
  const comments = await github.paginate(github.rest.issues.listComments, {
    owner, repo, issue_number, per_page: 100,
  });
  const previous = comments.find(comment =>
    comment.user?.login === 'github-actions[bot]' && comment.body?.startsWith(marker));
  const runId = Number(context.runId);
  const attempt = Number(env.GITHUB_RUN_ATTEMPT);
  const priorRun = previous?.body.match(/<!-- iac-plan-run:(\d+):(\d+) -->/);
  if (priorRun && (Number(priorRun[1]) > runId ||
      (Number(priorRun[1]) === runId && Number(priorRun[2]) > attempt))) {
    core.info('A newer run already published its plan comment.');
    return;
  }

  const body = `${marker}\n<!-- iac-plan-run:${runId}:${attempt} -->\n` +
    fs.readFileSync(env.PLAN_COMMENT_PATH, 'utf8');
  if (Buffer.byteLength(body, 'utf8') > 60000) {
    throw new Error('Plan preview exceeds the PR comment size limit.');
  }
  if (previous) {
    await github.rest.issues.updateComment({ owner, repo, comment_id: previous.id, body });
  } else {
    await github.rest.issues.createComment({ owner, repo, issue_number, body });
  }
};
