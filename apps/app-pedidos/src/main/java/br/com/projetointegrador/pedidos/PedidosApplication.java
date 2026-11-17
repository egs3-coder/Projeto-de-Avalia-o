package br.com.projetointegrador.pedidos;

import io.micrometer.observation.ObservationPredicate;
import io.micrometer.observation.ObservationRegistry;
import io.micrometer.observation.aop.ObservedAspect;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.server.observation.ServerRequestObservationContext;
import org.springframework.web.client.RestClient;

@SpringBootApplication
public class PedidosApplication {

    public static void main(String[] args) {
        SpringApplication.run(PedidosApplication.class, args);
    }

    /** Habilita a anotação @Observed: cada método anotado vira um span e uma métrica. */
    @Bean
    ObservedAspect observedAspect(ObservationRegistry registry) {
        return new ObservedAspect(registry);
    }

    /**
     * O RestClient.Builder do Spring Boot já vem instrumentado: cada chamada gera um span
     * cliente e propaga o cabeçalho W3C "traceparent" para o app-estoque, o que une os
     * dois serviços num único trace no Tempo.
     */
    @Bean
    RestClient estoqueClient(RestClient.Builder builder, @Value("${estoque.url}") String estoqueUrl) {
        return builder.baseUrl(estoqueUrl).build();
    }

    /**
     * Não gera traces/métricas HTTP para as chamadas do Prometheus em /actuator/**
     * (scrape a cada 15 s), evitando poluir o Tempo com traces sem valor.
     */
    @Bean
    ObservationPredicate ignorarActuator() {
        return (name, context) -> {
            if (context instanceof ServerRequestObservationContext servidor) {
                return !servidor.getCarrier().getRequestURI().startsWith("/actuator");
            }
            return true;
        };
    }
}
