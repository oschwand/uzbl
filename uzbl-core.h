/* -*- c-basic-offset: 4; -*-

 * See LICENSE for license details
 *
 * Changelog:
 * ---------
 *
 * (c) 2009 by Robert Manea
 *     - introduced struct concept
 *
 */

#define _POSIX_SOURCE

#include <glib/gstdio.h>
#include <gtk/gtk.h>
#include <gdk/gdkx.h>
#include <gdk/gdkkeysyms.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/un.h>
#include <sys/utsname.h>
#include <sys/time.h>
#include <webkit/webkit.h>
#include <libsoup/soup.h>
#include <JavaScriptCore/JavaScript.h>

#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include <stdlib.h>
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <assert.h>
#include <poll.h>
#include <sys/uio.h>
#include <sys/ioctl.h>
#include <assert.h>

#define LENGTH(x) (sizeof x / sizeof x[0])

/* status bar elements */
typedef struct {
    gint           load_progress;
    gchar          *msg;
} StatusBar;


/* gui elements */
typedef struct {
    GtkWidget*     main_window;
    gchar*         geometry;
    GtkPlug*       plug;
    GtkWidget*     scrolled_win;
    GtkWidget*     vbox;
    GtkWidget*     mainbar;
    GtkWidget*     mainbar_label;
    GtkScrollbar*  scbar_v;   // Horizontal and Vertical Scrollbar
    GtkScrollbar*  scbar_h;   // (These are still hidden)
    GtkAdjustment* bar_v; // Information about document length
    GtkAdjustment* bar_h; // and scrolling position
    WebKitWebView* web_view;
    gchar*         main_title;
    gchar*         icon;

    /* WebInspector */
    GtkWidget *inspector_window;
    WebKitWebInspector *inspector;

    StatusBar sbar;
} GUI;


/* external communication*/
enum { FIFO, SOCKET};
typedef struct {
    gchar          *fifo_path;
    gchar          *socket_path;
    /* stores (key)"variable name" -> (value)"pointer to this var*/
    GHashTable     *proto_var;

    gchar          *sync_stdout;
    GIOChannel     *clientchan;
} Communication;


/* internal state */
typedef struct {
    gchar    *uri;
    gchar    *config_file;
    int      socket_id;
    char     *instance_name;
    gchar    *selected_url;
    gchar    *last_selected_url;
    gchar    *executable_path;
    gchar*   keycmd;
    gchar*   searchtx;
    gboolean verbose;
    GPtrArray *event_buffer;
} State;


/* networking */
typedef struct {
    SoupSession *soup_session;
    SoupLogger *soup_logger;
    char *proxy_url;
    char *useragent;
    gint max_conns;
    gint max_conns_host;
} Network;


/* behaviour */
typedef struct {
    gchar*   load_finish_handler;
    gchar*   load_start_handler;
    gchar*   load_commit_handler;
    gchar*   status_format;
    gchar*   title_format_short;
    gchar*   title_format_long;
    gchar*   status_background;
    gchar*   fifo_dir;
    gchar*   socket_dir;
    gchar*   download_handler;
    gchar*   cookie_handler;
    gchar*   new_window;
    gchar*   default_font_family;
    gchar*   monospace_font_family;
    gchar*   sans_serif_font_family;
    gchar*   serif_font_family;
    gchar*   fantasy_font_family;
    gchar*   cursive_font_family;
    gchar*   scheme_handler;
    gboolean show_status;
    gboolean forward_keys;
    gboolean status_top;
    guint    modmask;
    guint    http_debug;
    gchar*   shell_cmd;
    guint    view_source;
    /* WebKitWebSettings exports */
    guint    font_size;
    guint    monospace_size;
    guint    minimum_font_size;
    gfloat   zoom_level;
    guint    disable_plugins;
    guint    disable_scripts;
    guint    autoload_img;
    guint    autoshrink_img;
    guint    enable_spellcheck;
    guint    enable_private;
    guint    print_bg;
    gchar*   style_uri;
    guint    resizable_txt;
    gchar*   default_encoding;
    guint    enforce_96dpi;
    gchar    *inject_html;
    guint    caret_browsing;
    guint    mode;
    gchar*   base_url;
    gboolean print_version;

    /* command list: (key)name -> (value)Command  */
    /* command list: (key)name -> (value)Command  */
    GHashTable* commands;
    /* event lookup: (key)event_id -> (value)event_name */
    GHashTable *event_lookup;
} Behaviour;

/* javascript */
typedef struct {
    gboolean            initialized;
    JSClassDefinition   classdef;
    JSClassRef          classref;
} Javascript;

/* static information */
typedef struct {
    int   webkit_major;
    int   webkit_minor;
    int   webkit_micro;
    gchar *arch;
    gchar *commit;
    gchar *pid_str;
} Info;

/* main uzbl data structure */
typedef struct {
    GUI           gui;
    State         state;
    Network       net;
    Behaviour     behave;
    Communication comm;
    Javascript    js;
    Info          info;

    Window        xwin;
} UzblCore;

/* Main Uzbl object */
extern UzblCore uzbl;

typedef void sigfunc(int);

typedef struct {
    char* name;
    char* param;
} Action;

/* XDG Stuff */
typedef struct {
    gchar* environmental;
    gchar* default_value;
} XDG_Var;


/* Functions */
char *
itos(int val);

char *
str_replace (const char* search, const char* replace, const char* string);

gchar*
strfree(gchar *str);

GArray*
read_file_by_line (const gchar *path);

gchar*
parseenv (char* string);

void
clean_up(void);

void
catch_sigterm(int s);

sigfunc *
setup_signal(int signe, sigfunc *shandler);

gchar*
parseenv (char* string);

gboolean
set_var_value(const gchar *name, gchar *val);

void
print(WebKitWebView *page, GArray *argv, GString *result);

void
commands_hash(void);

void
free_action(gpointer act);

Action*
new_action(const gchar *name, const gchar *param);

bool
file_exists (const char * filename);

void
set_keycmd();

void
load_uri (WebKitWebView * web_view, GArray *argv, GString *result);

void
new_window_load_uri (const gchar * uri);

void
chain (WebKitWebView *page, GArray *argv, GString *result);

void
close_uzbl (WebKitWebView *page, GArray *argv, GString *result);

gboolean
run_command(const gchar *command, const guint npre,
            const gchar **args, const gboolean sync, char **output_stdout);

void
talk_to_socket(WebKitWebView *web_view, GArray *argv, GString *result);

void
spawn(WebKitWebView *web_view, GArray *argv, GString *result);

void
spawn_sh(WebKitWebView *web_view, GArray *argv, GString *result);

void
spawn_sync(WebKitWebView *web_view, GArray *argv, GString *result);

void
spawn_sh_sync(WebKitWebView *web_view, GArray *argv, GString *result);

void
parse_command(const char *cmd, const char *param, GString *result);

void
parse_cmd_line(const char *ctl_line, GString *result);

/*@null@*/ gchar*
build_stream_name(int type, const gchar *dir);

gboolean
control_fifo(GIOChannel *gio, GIOCondition condition);

/*@null@*/ gchar*
init_fifo(gchar *dir);

gboolean
control_stdin(GIOChannel *gio, GIOCondition condition);

void
create_stdin();

/*@null@*/ gchar*
init_socket(gchar *dir);

gboolean
control_socket(GIOChannel *chan);

gboolean
control_client_socket(GIOChannel *chan);

void
update_title (void);

gboolean
key_press_cb (GtkWidget* window, GdkEventKey* event);

gboolean
key_release_cb (GtkWidget* window, GdkEventKey* event);

void
run_keycmd(const gboolean key_ret);

void
initialize (int argc, char *argv[]);

void
create_browser ();

GtkWidget*
create_mainbar ();

GtkWidget*
create_window ();

GtkPlug*
create_plug ();

void
run_handler (const gchar *act, const gchar *args);

/*@null@*/ gchar*
get_xdg_var (XDG_Var xdg);

/*@null@*/ gchar*
find_xdg_file (int xdg_type, const char* filename);

void
settings_init ();

void
search_text (WebKitWebView *page, GArray *argv, const gboolean forward);

void
search_forward_text (WebKitWebView *page, GArray *argv, GString *result);

void
search_reverse_text (WebKitWebView *page, GArray *argv, GString *result);

void
dehilight (WebKitWebView *page, GArray *argv, GString *result);

void
run_js (WebKitWebView * web_view, GArray *argv, GString *result);

void
run_external_js (WebKitWebView * web_view, GArray *argv, GString *result);

void
eval_js(WebKitWebView * web_view, gchar *script, GString *result);

void handle_cookies (SoupSession *session,
                            SoupMessage *msg,
                            gpointer     user_data);
void
save_cookies (SoupMessage *msg, gpointer     user_data);

void
set_var(WebKitWebView *page, GArray *argv, GString *result);

void
act_dump_config();

void
act_dump_config_as_events();

void
dump_var_hash(gpointer k, gpointer v, gpointer ud);

void
dump_key_hash(gpointer k, gpointer v, gpointer ud);

void
dump_config();

void
dump_config_as_events();

void
retrieve_geometry();

void
update_gui(WebKitWebView *page, GArray *argv, GString *result);

void
event(WebKitWebView *page, GArray *argv, GString *result);

typedef void (*Command)(WebKitWebView*, GArray *argv, GString *result);
typedef struct {
    Command function;
    gboolean no_split;
} CommandInfo;

/* vi: set et ts=4: */
