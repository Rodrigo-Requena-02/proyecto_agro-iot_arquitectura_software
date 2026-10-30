#pragma once
#include <cstdio>
#include <cstdlib>
#include <cstdint>
#include <string>
#include <chrono>
#include <thread>
#include <unistd.h>
#include <sys/select.h>
typedef uint8_t byte;
#define F(x) x
#define A0 0
inline unsigned long millis(){ static auto t0=std::chrono::steady_clock::now(); return std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now()-t0).count(); }
inline long random(long a,long b){ return a + rand()%(b-a); }
inline void randomSeed(long s){ srand((unsigned)s); }
inline int analogRead(int){ return (int)time(0); }
struct SerialT {
  void begin(long){}
  void print(const char* s){ fputs(s,stdout);} void print(char c){ putchar(c);} void print(float v,int d){ printf("%.*f",d,v);}
  void println(const char* s){ fputs(s,stdout); putchar('\n'); fflush(stdout);} void println(char c){ putchar(c); putchar('\n'); fflush(stdout);}
  int available(){ fd_set f; FD_ZERO(&f); FD_SET(0,&f); timeval tv{0,0}; return select(1,&f,0,0,&tv)>0 ? 1:0; }
  int read(){ char c; return read_(c)? c:-1; }
  bool read_(char&c){ return ::read(0,&c,1)==1; }
};
static SerialT Serial;
void setup(); void loop();
