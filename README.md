# ArquiBot

Arquibot is a Wikipedia archive bot built with Django for the Brazilian Wikimedia community.

It monitors Portuguese Wikipedia (ptwiki) for new or unarchived external links in {{citar}} templates, automatically archives them using the Wayback Machine, and updates the articles with properly formatted archived citations. The bot also logs statistics into a Django database and provides a web interface for monitoring activity.

## Running locally

Enter the `src/` directory.

Copy `.env.sample` to `.env` and provide the environment variables.

To authenticate it locally, you will need to use the developer access. Request an access token at <https://api.wikimedia.org/wiki/Special:AppManagement>, click on "Create key". You should ask for a **Personal API token**, allow it to create and edit items and save. Copy the **Access token** to fill `ARQUIBOT_TOKEN`.

Setup a python virtual environment using `requirements.txt`. An easy way to do that is to run `nix-shell`.

### Available commands

* `python3 manage.py runserver` to see the web page with statistics
* `python3 manage.py run_article TITLE` to run for a specific article
* `python3 manage.py run_rc_date YYYY-MM-DD` to run on recent changes at a speficic date (UTC)
  * `run_rc_date` skips articles checked in the past 7 days
  * you can also make it stop after a certain number of edits `python manage.py run_rc_date YYYY-MM-DD --stop-at-edit-count 10`
* `python3 manage.py runner` will run everyday on yesterday's Recent Changes, waiting until the next day to run again. Continuous command.

## Toolforge deployment

Deployed as a regular python django app on Toolforge, through `.github/workflows/toolforge-deploy.yml`. The `runner` continuous command is run through uwsgi daemons.
